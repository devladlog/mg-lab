import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "fs";
import * as path from "path";
import { hasUnquotedSeparator, lintFiles, lintQuery, unquote } from "../src/lint";

const ROOT = path.resolve(__dirname, "../../.."); // src/pq-lint/dist/test -> src/
const QUERIES = path.join(ROOT, "queries");
const FIXTURES = path.resolve(ROOT, "../tests/fixtures/ui-generated");

function readFolder(folder: string): Map<string, string> {
    const files = new Map<string, string>();
    for (const f of fs.readdirSync(folder).filter((f) => f.endsWith(".pq"))) {
        files.set(path.basename(f, ".pq"), fs.readFileSync(path.join(folder, f), "utf8"));
    }
    return files;
}

const rules = (findings: { rule: string }[]) => findings.map((f) => f.rule).sort();

test("episode queries: zero findings", async () => {
    const files = readFolder(QUERIES);
    assert.equal(files.size, 9);
    assert.deepEqual(await lintFiles(files), []);
});

test("UI-generated fixture: every rule fires where expected", async () => {
    const findings = await lintFiles(readFolder(FIXTURES));
    const at = (query: string) => rules(findings.filter((f) => f.query === query));
    assert.deepEqual(at("Broken"), ["PQ001"]);
    assert.deepEqual(at("Dates"), ["PQ002", "PQ008"]);
    assert.deepEqual(at("Exports"), ["PQ002", "PQ003", "PQ004", "PQ005", "PQ006", "PQ007", "PQ007", "PQ007", "PQ007", "PQ007"]);
});

test("PQ001 reports the line of the syntax error", async () => {
    const [f] = await lintQuery("q", "let\n    a = 1,\n    b = Table.SelectRows(a, each [x] > )\nin\n    b", new Set());
    assert.equal(f.rule, "PQ001");
    assert.equal(f.line, 3);
});

test("PQ002 catches a typo in a query reference", async () => {
    const text = fs.readFileSync(path.join(QUERIES, "Sales.pq"), "utf8").replace(", Product, ", ", Prodcut, ");
    const files = readFolder(QUERIES);
    files.set("Sales", text);
    const findings = await lintFiles(files);
    assert.equal(findings.length, 1);
    assert.equal(findings[0].rule, "PQ002");
    assert.match(findings[0].message, /"Prodcut"/);
});

test("PQ002 understands let steps, function arguments, each and record fields", async () => {
    const text = `let
        f = (t as table, n) => Table.FirstN(t, n),
        r = [a = 1, b = a + 1],
        rows = Table.SelectRows(Source, each [x] = r[b] and _[y] <> null),
        #"Step with spaces" = f(rows, 3),
        d = #date(2025, 1, 1) + #duration(1, 0, 0, 0)
    in
        #"Step with spaces"`;
    assert.deepEqual(rules(await lintQuery("q", text, new Set(["Source"]))), []);
    assert.deepEqual(rules(await lintQuery("q", text, new Set())), ["PQ002"]); // Source unknown
});

test("PQ003 flags absolute paths, not parameters or relative names", async () => {
    const known = new Set(["Folder"]);
    assert.deepEqual(rules(await lintQuery("q", `File.Contents("\\\\server\\share\\a.csv")`, known)), ["PQ003"]);
    assert.deepEqual(rules(await lintQuery("q", `File.Contents("/mnt/data/a.csv")`, known)), ["PQ003"]);
    assert.deepEqual(rules(await lintQuery("q", `File.Contents(Folder & "a.csv")`, known)), []);
});

test("PQ004 fires for Sort then Distinct, not for Sort, Buffer, Distinct", async () => {
    const bad = `let s = Table.Sort(T, {{"F", Order.Descending}}), d = Table.Distinct(s, {"K"}) in d`;
    const inline = `Table.Distinct(Table.Sort(T, {{"F", Order.Descending}}), {"K"})`;
    const good = `let s = Table.Sort(T, {{"F", Order.Descending}}), b = Table.Buffer(s), d = Table.Distinct(b, {"K"}) in d`;
    const known = new Set(["T"]);
    assert.deepEqual(rules(await lintQuery("q", bad, known)), ["PQ004"]);
    assert.deepEqual(rules(await lintQuery("q", inline, known)), ["PQ004"]);
    assert.deepEqual(rules(await lintQuery("q", good, known)), []);
});

test("PQ005 wants the culture argument", async () => {
    const known = new Set(["T"]);
    assert.deepEqual(rules(await lintQuery("q", `Table.TransformColumnTypes(T, {{"A", Int64.Type}})`, known)), ["PQ005"]);
    assert.deepEqual(rules(await lintQuery("q", `Table.TransformColumnTypes(T, {{"A", Int64.Type}}, "en-US")`, known)), []);
});

test("PQ006: Folder.Files needs an Extension filter", async () => {
    const known = new Set(["F"]);
    assert.deepEqual(rules(await lintQuery("q", `Folder.Files(F)`, known)), ["PQ006"]);
    assert.deepEqual(rules(await lintQuery("q", `Table.SelectRows(Folder.Files(F), each [Extension] = ".csv")`, known)), []);
});

test("PQ007 matches generated names with or without a number", async () => {
    const text = `let #"Changed Type2" = 1, #"Expanded Data" = 2, Typed = 3 in Typed`;
    assert.deepEqual(rules(await lintQuery("q", text, new Set())), ["PQ007", "PQ007"]);
});

test("PQ008 only when a culture is given and the separator isn't quoted", async () => {
    const q = (fmt: string, culture = `, Culture = "pt-PT"`) => `Date.FromText("01/02/2025", [Format = "${fmt}"${culture}])`;
    assert.deepEqual(rules(await lintQuery("q", q("dd/MM/yyyy"), new Set())), ["PQ008"]);
    assert.deepEqual(rules(await lintQuery("q", q("dd'/'MM'/'yyyy"), new Set())), []);
    assert.deepEqual(rules(await lintQuery("q", q("dd/MM/yyyy", ""), new Set())), []);
});

test("helpers", () => {
    assert.equal(unquote('#"Changed Type"'), "Changed Type");
    assert.equal(unquote('#"say ""hi"""'), 'say "hi"');
    assert.equal(unquote("Source"), "Source");
    assert.equal(hasUnquotedSeparator("dd/MM/yyyy"), true);
    assert.equal(hasUnquotedSeparator("dd'/'MM'/'yyyy"), false);
    assert.equal(hasUnquotedSeparator("dd\\/MM\\/yyyy"), false);
    assert.equal(hasUnquotedSeparator("HH:mm"), true);
    assert.equal(hasUnquotedSeparator("yyyy-MM-dd"), false);
});
