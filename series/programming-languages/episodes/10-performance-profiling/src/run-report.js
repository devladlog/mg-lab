// Plain script for `node --cpu-prof`: node --cpu-prof --cpu-prof-dir=profiles src/run-report.js slow 3000
import { generateRequests } from "#src/data.js";
import { buildReportFast, buildReportSlow } from "#src/report.js";

const [impl = "slow", rows = "3000"] = process.argv.slice(2);
const build = { slow: buildReportSlow, fast: buildReportFast }[impl];
if (!build) { console.error("usage: run-report.js <slow|fast> [rows]"); process.exit(2); }
const requests = generateRequests(Number(rows));
const started = performance.now();
const report = build(requests);
console.log(`${impl}: ${report.lines.length} lines, ${report.duplicates.length} duplicates, ${(performance.now() - started).toFixed(0)} ms`);
