import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:net";
import { ApprovalsClient } from "#src/client.js";
import { ApiError } from "#src/errors.js";
import { startApi, noWait, eventually } from "./helpers.js";

test("200: returns the approvers for a department, case-insensitive", async () => {
  const { api, url } = await startApi({ latencyMs: 1 });
  try {
    const people = await new ApprovalsClient(url).approversFor("it");
    assert.equal(people.manager, "Alex Demo");
    assert.equal(people.board, "Taylor Demo");
  } finally { await api.close(); }
});

test("503 on the first call is retried with backoff, and the retry succeeds", async () => {
  const { api, url } = await startApi({ latencyMs: 1, failFirst: ["operations"] });
  const waits = [];
  try {
    const client = new ApprovalsClient(url, { random: () => 0.5, baseDelayMs: 100, wait: async (ms) => { waits.push(ms); } });
    const people = await client.approversFor("Operations");
    assert.equal(people.manager, "Jordan Demo");
    assert.deepEqual(waits, [50]);                       // 0.5 * 100 * 2^0
    assert.equal(api.stats.calls, 2);
  } finally { await api.close(); }
});

test("404 is not retried", async () => {
  const { api, url } = await startApi({ latencyMs: 1 });
  try {
    await assert.rejects(new ApprovalsClient(url, { wait: noWait }).approversFor("Legal"), (e) => e instanceof ApiError && e.status === 404 && !e.retryable);
    assert.equal(api.stats.calls, 1);
  } finally { await api.close(); }
});

test("a slow API hits the deadline, is retried once, and the server sees every call cancelled", async () => {
  const { api, url } = await startApi({ latencyMs: 1500 });
  try {
    let waits = 0;
    const client = new ApprovalsClient(url, { timeoutMs: 100, retries: 1, wait: async () => { waits++; } });
    await assert.rejects(client.approversFor("IT"), (e) => e instanceof ApiError && /timeout after 100 ms/.test(e.message) && e.cause.name === "TimeoutError");
    assert.equal(waits, 1);                              // exactly one retry, then give up
    await eventually(() => api.stats.calls >= 1 && api.stats.aborted === api.stats.calls);   // no call was left running
  } finally { await api.close(); }
});

test("a caller abort is passed through untouched and never retried", async () => {
  const { api, url } = await startApi({ latencyMs: 500 });
  try {
    const ctl = new AbortController();
    const pending = new ApprovalsClient(url, { wait: noWait }).approversFor("IT", { signal: ctl.signal });
    await eventually(() => api.stats.inFlight === 1);    // abort only once the server is really waiting
    ctl.abort(new Error("user pressed Ctrl+C"));
    await assert.rejects(pending, { message: "user pressed Ctrl+C" });
    await eventually(() => api.stats.aborted === 1);
    assert.equal(api.stats.calls, 1);
  } finally { await api.close(); }
});

test("gotcha: a refused connection is just 'fetch failed'; the real reason is in error.cause", async () => {
  const probe = createServer();
  await new Promise((r) => probe.listen(0, "127.0.0.1", r));
  const { port } = probe.address();
  await new Promise((r) => probe.close(r));              // the port is now free: nothing listens there
  let raw;
  try { await fetch(`http://127.0.0.1:${port}/`); } catch (e) { raw = e; }
  assert.equal(raw.message, "fetch failed");
  assert.equal(raw.cause.code, "ECONNREFUSED");
  const wrapped = await new ApprovalsClient(`http://127.0.0.1:${port}`, { retries: 0 }).approversFor("IT").catch((e) => e);
  assert.match(wrapped.message, /network error: ECONNREFUSED/);
  assert.equal(wrapped.retryable, true);
});
