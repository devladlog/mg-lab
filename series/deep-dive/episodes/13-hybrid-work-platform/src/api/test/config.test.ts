import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { LIMITS, loadConfig } from "../src/lib/config";
import { readSiteFile, resolveAsset } from "../src/lib/assets";

const contract = JSON.parse(readFileSync(path.join(__dirname, "..", "..", "..", "..", "contract", "hybrid.json"), "utf8"));

test("limits in the API equal the contract file", () => {
  assert.deepEqual(LIMITS.invite, contract.invite);
  assert.deepEqual([...LIMITS.token.scopes], contract.token.scopes);
  assert.equal(LIMITS.token.expiresInMinutes, contract.token.expiresInMinutes);
  assert.deepEqual([...LIMITS.token.allowedMeetingHosts], contract.token.allowedMeetingHosts);
});

test("token lifetime is inside the Identity SDK range of 60 to 1440 minutes (the default would be 24 hours)", () => {
  assert.ok(LIMITS.token.expiresInMinutes >= 60 && LIMITS.token.expiresInMinutes <= 1440);
  assert.ok(LIMITS.token.expiresInMinutes < 1440, "must be shorter than the SDK default of 24 hours");
});

test("config: missing settings are named; keys and connection strings are refused", () => {
  assert.throws(() => loadConfig({}), /Acs__Endpoint, Invites__TableEndpoint/);
  assert.throws(() => loadConfig({ Acs__Endpoint: "endpoint=https://x.communication.azure.com/;accesskey=abc", Invites__TableEndpoint: "https://s.table.core.windows.net" }), /no keys/);
  assert.throws(() => loadConfig({ Acs__Endpoint: "http://evil.example", Invites__TableEndpoint: "https://s.table.core.windows.net" }));
  const cfg = loadConfig({ Acs__Endpoint: "https://acs-hyb-abc.europe.communication.azure.com/", Invites__TableEndpoint: "https://s.table.core.windows.net" });
  assert.equal(cfg.tableName, "invites");
});

test("assets: only the two allow-listed names resolve, including names that look like prototype keys", () => {
  assert.ok(resolveAsset("join.js"));
  assert.ok(resolveAsset("join.css"));
  for (const name of ["", "index.html", "../join.js", "..%2fjoin.js", "join.js/", "constructor", "__proto__", "toString", "hasOwnProperty"]) {
    assert.equal(resolveAsset(name), undefined, name);
  }
});

test("assets: readSiteFile reads from the site folder only", async () => {
  await assert.rejects(readSiteFile(__dirname, "does-not-exist.html"));
});

test("source never touches an ACS key or connection string and never reads the tenant or meeting from headers", () => {
  const srcDir = path.join(__dirname, "..", "..", "src"); // build-test/test -> src/api/src
  const files = ["lib/runtime.ts", "lib/token.ts", "lib/handlers.ts", "lib/tableStore.ts", "functions/token.ts", "functions/invites.ts"];
  for (const f of files) {
    const text = readFileSync(path.join(srcDir, f), "utf8");
    assert.ok(!/AzureKeyCredential|connectionString|CONNECTION_STRING|accesskey/i.test(text), `${f} must use Entra auth only`);
    assert.ok(!/headers\.get\(|request\.headers/.test(text), `${f} must not read identity from headers`);
  }
});
