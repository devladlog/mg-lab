import { readFile } from "node:fs/promises";
import { intake } from "./intake.js";
import { summary } from "./workflow.js";

// noUncheckedIndexedAccess: argv[2] is `string | undefined`, so we have to handle the missing case.
const file = process.argv[2];
if (file === undefined) {
  console.error("Usage: npm run intake -- <requests.json>");
  process.exit(2);
}

let data: unknown;
try {
  data = JSON.parse(await readFile(file, "utf8"));
} catch (error) {
  // useUnknownInCatchVariables: `error` is unknown, not any. Narrow it before use.
  console.error(`Can't read ${file}: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(2);
}

if (!Array.isArray(data)) {
  console.error("Expected a JSON array of requests.");
  process.exit(2);
}

const lines = intake(data, 2026);
for (const line of lines) {
  if (line.kind === "accepted") {
    console.log(`  OK  ${summary(line.request)}`);
  } else {
    const details = line.errors.map((e) => `${e.field}: ${e.message}`).join(" | ");
    console.log(` ERR  item ${line.index}  ${details}`);
  }
}

const rejected = lines.filter((l) => l.kind === "rejected").length;
console.log(`\n${lines.length - rejected} accepted, ${rejected} rejected`);
process.exitCode = rejected > 0 ? 1 : 0;
