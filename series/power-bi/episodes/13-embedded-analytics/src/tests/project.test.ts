// Files the demo depends on: the page only loads scripts the server serves, and the roles match episode 5's model.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import { defaultStaticFiles } from "../server/app.js";
import { APP_USERS } from "../server/lab-users.js";

const root = path.resolve(import.meta.dirname, "..", "..");

test("index.html only references scripts that the server serves", async () => {
  const html = await readFile(path.join(root, "public", "index.html"), "utf8");
  const served = Object.keys(defaultStaticFiles(root).routes);
  const srcs = [...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(srcs.length >= 2);
  for (const s of srcs) assert.ok(served.includes(s as string), `${s} is not a served route`);
});

test("the built client and powerbi-client are where the server looks (after npm ci and tsc)", (t) => {
  const routes = defaultStaticFiles(root).routes;
  for (const url of ["/embed.js", "/timing.js", "/vendor/powerbi.js"]) {
    assert.ok(existsSync(routes[url]!.file), `${url} -> ${routes[url]!.file}`);
  }
  t.diagnostic("built files present");
});

test("powerbi.js really defines window.powerbi and window['powerbi-client'] with TokenType.Embed and Permissions.Read", async () => {
  const code = await readFile(defaultStaticFiles(root).routes["/vendor/powerbi.js"]!.file, "utf8");
  const win: Record<string, unknown> = { crypto: webcrypto, navigator: { userAgent: "node" }, document: { addEventListener() {}, createElement: () => ({}) }, location: {}, addEventListener() {} };
  win["window"] = win;
  win["self"] = win;
  vm.runInNewContext(code, win, { timeout: 10000 });
  const pbi = win["powerbi-client"] as { models: { TokenType: { Embed: number }; Permissions: { Read: number } } };
  assert.equal(pbi.models.TokenType.Embed, 1);
  assert.equal(pbi.models.Permissions.Read, 0);
  const service = win["powerbi"] as Record<string, unknown>;
  for (const m of ["embed", "reset", "load"]) assert.equal(typeof service[m], "function", m);
});

test("the app's users and roles match episode 5's role_members.csv", async () => {
  const csv = await readFile(path.join(root, "..", "..", "05-row-level-security", "src", "data", "role_members.csv"), "utf8").catch(() => "");
  if (!csv) return; // episode folder copied alone
  const rows = csv.trim().split(/\r?\n/).slice(1).map((l) => l.split(","));
  for (const [alias, role] of rows) {
    const u = APP_USERS.find((x) => x.alias === alias);
    assert.ok(u, `${alias} missing from lab-users.ts`);
    assert.deepEqual(u.roles, [role]);
  }
});
