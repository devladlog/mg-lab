import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCsv, splitLine } from "#src/csv.js";
import { validateRow, priorityFor } from "#src/domain.js";

test("splitLine handles quotes, commas inside quotes and doubled quotes", () => {
  assert.deepEqual(splitLine('a,"b,c",d'), ["a", "b,c", "d"]);
  assert.deepEqual(splitLine('"say ""hi""",x'), ['say "hi"', "x"]);
  assert.deepEqual(splitLine("a,,c"), ["a", "", "c"]);
});

test("parseCsv works on a plain array and on an async generator, and numbers rows from the header", async () => {
  async function* lines() { yield "a,b"; yield ""; yield "1,2"; yield "3,4"; }
  const fromAsync = [];
  for await (const r of parseCsv(lines())) fromAsync.push(r);
  assert.deepEqual(fromAsync, [{ row: 3, record: { a: "1", b: "2" } }, { row: 4, record: { a: "3", b: "4" } }]);
  const fromArray = [];
  for await (const r of parseCsv(["a", "x"])) fromArray.push(r);
  assert.equal(fromArray[0].row, 2);
});

const good = { code: "PR-2026-0301", title: "Laptop refresh", department: "IT", budget: "12000", submitted: "2026-11-02" };

test("priority boundaries: 49,999.99 Standard, 50,000 High, 250,000 Board", () => {
  const p = (budget) => validateRow({ row: 2, record: { ...good, budget } }).request.priority;
  assert.equal(p("49999.99"), "Standard");
  assert.equal(p("50000"), "High");
  assert.equal(p("249999.99"), "High");
  assert.equal(p("250000"), "Board");
  assert.equal(priorityFor(0), "Standard");
});

test('"75,000" is accepted as 75000, "abc" and "-500" are not', () => {
  assert.equal(validateRow({ row: 2, record: { ...good, budget: "75,000" } }).request.budgetCents, 7_500_000);
  const abc = validateRow({ row: 9, record: { ...good, budget: "abc" } });
  assert.equal(abc.ok, false);
  assert.match(abc.errors[0].message, /row 9: budget: "abc" is not a number/);
  assert.match(validateRow({ row: 10, record: { ...good, budget: "-500" } }).errors[0].message, /greater than zero/);
});

test("every problem in a row is reported, not just the first", () => {
  const r = validateRow({ row: 5, record: { code: "REQ-77", title: "", department: "IT", budget: "x", submitted: "2026-13-01" } });
  assert.deepEqual(r.errors.map((e) => e.field), ["code", "title", "budget", "submitted"]);
  assert.ok(r.errors.every((e) => e.row === 5));
});

test("2026-02-30 is not a real date", () => {
  assert.equal(validateRow({ row: 2, record: { ...good, submitted: "2026-02-30" } }).ok, false);
  assert.equal(validateRow({ row: 2, record: { ...good, submitted: "2028-02-29" } }).ok, true);
});
