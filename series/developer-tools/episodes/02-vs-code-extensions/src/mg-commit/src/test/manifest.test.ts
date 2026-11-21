import { test } from "node:test";
import * as assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..", "..");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const source = readFileSync(join(root, "src", "extension.ts"), "utf8");

const minor = (range: string) => Number(/(\d+)\.(\d+)/.exec(range)![2]);

test("every contributed command is registered in extension.ts, and vice versa", () => {
  const contributed = pkg.contributes.commands.map((c: { command: string }) => c.command).sort();
  const registered = [...source.matchAll(/registerCommand\("([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(registered, contributed);
});

test("menus only reference contributed commands", () => {
  const contributed = new Set(pkg.contributes.commands.map((c: { command: string }) => c.command));
  for (const items of Object.values(pkg.contributes.menus) as Array<Array<{ command: string }>>) {
    for (const item of items) assert.ok(contributed.has(item.command), item.command);
  }
});

test("no activationEvents: contributed commands activate the extension (VS Code 1.74+)", () => {
  assert.equal(pkg.activationEvents, undefined);
  assert.ok(minor(pkg.engines.vscode) >= 74);
});

test("@types/vscode is not newer than engines.vscode (vsce refuses to package otherwise)", () => {
  assert.ok(minor(pkg.devDependencies["@types/vscode"]) <= minor(pkg.engines.vscode));
});

test("settings defaults are valid commit types", () => {
  for (const t of pkg.contributes.configuration.properties["mgCommit.types"].default) assert.match(t, /^[a-z]+$/);
});

test("main points at the compiled entry point", () => {
  assert.equal(pkg.main, "./out/extension.js");
  assert.ok(existsSync(join(root, "out", "extension.js")), "run npm run compile first");
});
