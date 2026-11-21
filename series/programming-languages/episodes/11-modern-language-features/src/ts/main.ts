import { readFileSync } from "node:fs";
import { buildDigest, render } from "./digest.ts";
import { parseRequests } from "./types.ts";

const [path] = process.argv.slice(2);
if (path === undefined) {
  console.error("usage: node src/ts/main.ts <requests.json>");
  process.exit(2);
}
process.stdout.write(render(buildDigest(parseRequests(readFileSync(path, "utf8")))));
