// Compiles a Deneb (Vega-Lite) spec with Vega-Lite's own compiler, runs it headless in Vega with the rows Deneb would
// pass in the "dataset" data source, and prints the derived rows as JSON. Fails on any compile warning.
// Usage: node check-spec.mjs <spec.vl.json> [--rows rows.json] [--tolerance 0.02]
import { readFileSync } from "node:fs";
import * as vl from "vega-lite";
import * as vega from "vega";

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const spec = JSON.parse(readFileSync(args[0], "utf8"));
const tolerance = opt("--tolerance");
if (tolerance !== undefined) spec.params.find((p) => p.name === "tolerance").value = Number(tolerance);
// Default rows: 2025 vs 2024 by category, as tests/test_expected.py computes them from the generated data.
const rows = opt("--rows") ? JSON.parse(readFileSync(opt("--rows"), "utf8")) : [
    { "Category": "Accessories", "Sales Amount": 130320.98, "Sales PY": 120256.62 },
    { "Category": "Bikes", "Sales Amount": 780356.80, "Sales PY": 716095.45 },
    { "Category": "Clothing", "Sales Amount": 56795.10, "Sales PY": 58577.03 },
];

const warnings = [];
const logger = { level() { return this; }, warn(...m) { warnings.push(m.join(" ")); return this; }, info() { return this; }, debug() { return this; }, error(...m) { throw new Error(m.join(" ")); } };
const compiled = vl.compile(spec, { logger }).spec;
if (warnings.length) { console.error("Vega-Lite warnings:\n" + warnings.join("\n")); process.exit(2); }

const view = new vega.View(vega.parse(compiled), { renderer: "none" });
view.data("dataset", rows.map((r, i) => ({ ...r, __row__: i })));   // Deneb adds __row__ to every row
await view.runAsync();
const derived = compiled.data.find((d) => (d.transform ?? []).some((t) => t.type === "formula" && t.as === "Band"));
const out = view.data(derived.name).map((d) => ({ Category: d.Category, Variance: d.Variance, Band: d.Band, Label: d.Label }));
console.log(JSON.stringify({ vegaLite: vl.version, vega: vega.version, marks: compiled.marks.length, rows: out }, null, 2));
