// Bundles the page into ../api/site (served by the join/asset functions). `--check` builds to memory and verifies the result.
import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const check = process.argv.includes("--check");
const outDir = path.join(here, "..", "api", "site");

const result = await build({
  entryPoints: [path.join(here, "src", "join.ts")],
  bundle: true,
  minify: true,
  platform: "browser",
  target: ["es2020"],
  format: "iife",
  write: !check,
  outfile: path.join(outDir, "join.js"),
  legalComments: "none",
  metafile: true,
  logLevel: "warning",
});

if (check) {
  const kb = Object.values(result.metafile.outputs)[0].bytes / 1024;
  console.log(`bundle ok: ${kb.toFixed(0)} KB`);
  if (kb < 50) throw new Error("bundle is suspiciously small: the Calling SDK was not bundled");
} else {
  mkdirSync(outDir, { recursive: true });
  copyFileSync(path.join(here, "src", "index.html"), path.join(outDir, "index.html"));
  copyFileSync(path.join(here, "src", "join.css"), path.join(outDir, "join.css"));
  console.log("site written to", outDir);
}
