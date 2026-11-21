// Local runner for an Office Script, used by the tests (python excelfake calls it for "Run script").
//
//   node run-script.mjs < request.json > response.json
//   request:  {"script": "UpsertPrices.ts", "tables": {"Catalogue": {"headers": [...], "rows": [[...]]}},
//              "args": [prices, supplier, sourceFile]}
//   response: {"ok": true, "result": ..., "tables": {...}, "writes": {"setValues": 1, "addRows": 1}, "logs": []}
//          or {"ok": false, "error": "..."}
//
// It strips the TypeScript types with Node's built-in stripTypeScriptTypes (Node 22.13+), runs the
// script's main() in a sandbox that has no fetch (Learn: external calls fail when a script runs from
// Power Automate), and gives it an in-memory ExcelScript workbook that implements only the members
// UpsertPrices.ts uses, with Excel's documented rules: getTable returns undefined for an unknown name,
// setValues needs the exact range size, values are string | number | boolean, and a string that starts
// with "=", "+" or "-" becomes a formula. It is a test double, not Excel.
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));

function cellOk(v) {
  return typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

function store(v) {
  // Learn (Range.setValues): a value starting with +, - or = is interpreted as a formula.
  if (typeof v === "string" && /^[=+\-]/.test(v)) return { formula: v };
  return v;
}

function makeWorkbook(tables, writes) {
  const make = (name, t) => {
    const width = t.headers.length;
    const range = (getRows, setRows) => ({
      getValues: () => getRows().map((r) => r.map((c) => (c && typeof c === "object" ? "#NAME?" : c))),
      setValues: (values) => {
        const rows = getRows();
        if (!Array.isArray(values) || values.length !== rows.length || values.some((r) => r.length !== width)) {
          throw new Error("The number of rows or columns in the input array doesn't match the size or dimensions of the range.");
        }
        values.forEach((r) => r.forEach((c) => { if (!cellOk(c)) throw new Error(`Invalid cell value: ${JSON.stringify(c)}`); }));
        writes.setValues++;
        setRows(values.map((r) => r.map(store)));
      },
      getRowCount: () => getRows().length,
    });
    return {
      getName: () => name,
      getHeaderRowRange: () => range(() => [t.headers], () => { throw new Error("headers are read-only here"); }),
      getRangeBetweenHeaderAndTotal: () => {
        if (t.rows.length === 0) throw new Error("This harness has no blank 'insert row': check getRowCount() first.");
        return range(() => t.rows, (v) => { t.rows = v; });
      },
      getRowCount: () => t.rows.length,
      addRows: (index, values) => {
        if (index !== undefined && index !== null && index !== -1) throw new Error("this harness only appends (index -1)");
        (values || []).forEach((r) => {
          if (r.length !== width) throw new Error("The number of columns in the row doesn't match the table.");
          r.forEach((c) => { if (!cellOk(c)) throw new Error(`Invalid cell value: ${JSON.stringify(c)}`); });
        });
        writes.addRows++;
        t.rows.push(...(values || []).map((r) => r.map(store)));
      },
    };
  };
  return { getTable: (key) => (tables[key] ? make(key, tables[key]) : undefined) };
}

const req = JSON.parse(readFileSync(0, "utf8"));
const source = readFileSync(resolve(here, req.script || "UpsertPrices.ts"), "utf8");
const writes = { setValues: 0, addRows: 0 };
const logs = [];
const tables = req.tables || {};
let out;
try {
  const js = stripTypeScriptTypes(source);
  const sandbox = {
    workbook: makeWorkbook(tables, writes),
    args: req.args || [],
    console: { log: (...a) => logs.push(a.map(String).join(" ")) },
  };
  vm.createContext(sandbox); // fresh realm: no fetch, no require, no process
  vm.runInContext(`${js}\n;globalThis.__result = main(workbook, ...args);`, sandbox, { timeout: 120000 });
  out = { ok: true, result: sandbox.__result, tables, writes, logs };
} catch (e) {
  out = { ok: false, error: `${e && e.message ? e.message : e}`, writes, logs };
}
process.stdout.write(JSON.stringify(out));
