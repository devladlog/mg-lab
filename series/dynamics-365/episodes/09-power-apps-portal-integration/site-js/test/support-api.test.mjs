import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const factory = createRequire(import.meta.url)("../support-api.js");

// Test doubles only: the demo runs this file's code in a page of the real Power Pages site.
function makeEnv({ token = "tok-123", responses = [] } = {}) {
  const calls = [];
  const env = {
    shell: { getTokenDeferred: () => ({ done(f) { f(token); return { fail() {} }; } }) },
    fetch: async (url, init) => {
      calls.push({ url, init });
      return responses.shift() ?? { ok: true, status: 200, json: async () => ({ value: [] }), headers: new Map() };
    },
  };
  return { api: factory(env), calls };
}

test("casesUrl always selects explicit columns and never uses a wildcard", () => {
  const { api } = makeEnv();
  const u = api.casesUrl({ top: 5, openOnly: true });
  assert.match(u, /^\/_api\/incidents\?\$select=title,description,prioritycode,createdon,statecode,ticketnumber/);
  assert.ok(u.includes("$top=5") && u.includes("$filter=statecode eq 0"));
  assert.ok(!u.includes("*"));
});

test("every request carries the anti-forgery token header", async () => {
  const { api, calls } = makeEnv();
  await api.listCases({ top: 3 });
  assert.equal(calls[0].init.headers["__RequestVerificationToken"], "tok-123");
  assert.equal(calls[0].init.credentials, "same-origin");
});

test("createCase posts a contact bind and returns the entityid header", async () => {
  const headers = new Map([["entityid", "00000000-0000-0000-0000-0000000000aa"]]);
  const { api, calls } = makeEnv({ responses: [{ ok: true, status: 204, headers }] });
  const id = await api.createCase({ title: "Till offline", contactId: "00000000-0000-0000-0000-000000000001", priority: 1 });
  assert.equal(id, "00000000-0000-0000-0000-0000000000aa");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body["customerid_contact@odata.bind"], "/contacts(00000000-0000-0000-0000-000000000001)");
  assert.equal(body.prioritycode, 1);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
});

test("createCase validates before calling the server", async () => {
  const { api, calls } = makeEnv();
  await assert.rejects(api.createCase({ title: "", contactId: "x" }), /required/);
  await assert.rejects(api.createCase({ title: "x".repeat(201), contactId: "x" }), /200/);
  assert.equal(calls.length, 0);
});

test("a server error becomes an Error with the status and the message", async () => {
  const bad = { ok: false, status: 403, text: async () => JSON.stringify({ error: { message: "Attribute All Columns is not enabled for Web Api" } }) };
  const { api } = makeEnv({ responses: [bad] });
  await assert.rejects(api.listCases(), (e) => e.status === 403 && /not enabled for Web Api/.test(e.message));
});

test("a non-JSON error body is kept as text", () => {
  const { api } = makeEnv();
  assert.match(api.parseError(500, "gateway").message, /500: gateway/);
});

test("token failure rejects the call", async () => {
  const env = { shell: { getTokenDeferred: () => ({ done() { return { fail(f) { f(new Error("no token")); } }; } }) }, fetch: async () => { throw new Error("must not run"); } };
  await assert.rejects(factory(env).listCases(), /no token/);
});
