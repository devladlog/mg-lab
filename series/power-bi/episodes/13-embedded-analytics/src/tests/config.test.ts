import { test } from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../server/config.js";

const Z = "00000000-0000-0000-0000-000000000000";
const good = {
  PBI_TENANT_ID: Z,
  PBI_CLIENT_ID: "00000000-0000-0000-0000-000000000001",
  PBI_CLIENT_SECRET: "not-a-real-secret",
  PBI_WORKSPACE_ID: "00000000-0000-0000-0000-000000000002",
  PBI_REPORT_ID: "00000000-0000-0000-0000-000000000003",
  PBI_UPN_DOMAIN: "@contoso.example",
};

test("loads a complete environment and strips the leading @ of the domain", () => {
  const cfg = loadConfig(good);
  assert.equal(cfg.upnDomain, "contoso.example");
  assert.equal(cfg.port, 5173);
  assert.equal(cfg.tokenLifetimeMinutes, 15);
});

test("lists every problem at once and never prints the secret", () => {
  assert.throws(
    () => loadConfig({ PBI_CLIENT_SECRET: "super-secret-value", PBI_TENANT_ID: "nope", PORT: "99999", EMBED_LIFETIME_MINUTES: "0" }),
    (e: Error) => {
      assert.match(e.message, /PBI_TENANT_ID is not a GUID/);
      assert.match(e.message, /PBI_CLIENT_ID is not set/);
      assert.match(e.message, /PBI_REPORT_ID is not set/);
      assert.match(e.message, /PORT/);
      assert.match(e.message, /EMBED_LIFETIME_MINUTES/);
      assert.ok(!e.message.includes("super-secret-value"));
      return true;
    },
  );
});
