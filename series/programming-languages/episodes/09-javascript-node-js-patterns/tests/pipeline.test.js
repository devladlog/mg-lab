import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ApprovalsClient } from "#src/client.js";
import { buildPacks, runIntake } from "#src/pipeline.js";
import { startApi, noWait, eventually } from "./helpers.js";

const SAMPLE = fileURLToPath(new URL("../samples/requests.csv", import.meta.url));

async function withApi(options, fn) {
  const { api, url } = await startApi(options);
  const dir = await mkdtemp(join(tmpdir(), "intake-"));
  try { return await fn({ api, client: new ApprovalsClient(url, { wait: noWait, retries: 2 }), dir }); }
  finally { await api.close(); await rm(dir, { recursive: true, force: true }); }
}

test("sample file: 9 ready, 5 rejected, one API call per department (cache), NDJSON on disk", async () => {
  await withApi({ latencyMs: 5 }, async ({ api, client, dir }) => {
    const out = join(dir, "packs.ndjson");
    const { counts, cache } = await runIntake({ file: SAMPLE, out, client, concurrency: 4 });
    assert.deepEqual(counts, { ready: 9, rejected: 5, failed: 0 });
    assert.deepEqual(cache, { hits: 5, misses: 5 });
    assert.equal(api.stats.calls, 5);                    // IT, Operations, Marketing, HR, Legal
    const records = (await readFile(out, "utf8")).trim().split("\n").map((l) => JSON.parse(l));
    assert.equal(records.length, 14);
    const byCode = Object.fromEntries(records.filter((r) => r.code).map((r) => [r.code, r]));
    assert.deepEqual(byCode["PR-2026-0304"].route, ["Alex Demo", "Sam Demo", "Taylor Demo"]);   // 300,000: board joins
    assert.deepEqual(byCode["PR-2026-0301"].route, ["Alex Demo", "Sam Demo"]);
    assert.equal(byCode["PR-2026-0306"].budget, 75000);                                          // "75,000" and "it"
    assert.equal(byCode["PR-2026-0311"].status, "rejected");                                     // Legal: 404 from the API
    assert.equal(byCode["PR-2026-0314"].title, "Training, certifications");
  });
});

test("--no-cache style: one API call per valid row", async () => {
  await withApi({ latencyMs: 5 }, async ({ api, client, dir }) => {
    await runIntake({ file: SAMPLE, out: join(dir, "p.ndjson"), client, concurrency: 4, useCache: false });
    assert.equal(api.stats.calls, 10);
  });
});

test("concurrency is respected against the real API: max 3 calls in flight", async () => {
  await withApi({ latencyMs: 20 }, async ({ api, client, dir }) => {
    await runIntake({ file: SAMPLE, out: join(dir, "p.ndjson"), client, concurrency: 3, useCache: false });
    assert.equal(api.stats.maxInFlight, 3);
  });
});

test("a flaky department is retried and the batch still completes", async () => {
  await withApi({ latencyMs: 5, failFirst: ["operations"] }, async ({ api, client, dir }) => {
    const { counts } = await runIntake({ file: SAMPLE, out: join(dir, "p.ndjson"), client, concurrency: 4 });
    assert.deepEqual(counts, { ready: 9, rejected: 5, failed: 0 });
    assert.equal(api.stats.byDepartment.operations, 2);
  });
});

test("an API that stays down turns rows into 'failed' records, not into a crashed batch", async () => {
  const { api, url } = await startApi({ latencyMs: 1 });
  await api.close();                                      // nothing listens any more
  const client = new ApprovalsClient(url, { wait: noWait, retries: 1 });
  const records = [];
  for await (const r of buildPacks(["code,title,department,budget,submitted", "PR-2026-0001,Test,IT,100,2026-11-01"], { client })) records.push(r);
  assert.equal(records[0].status, "failed");
  assert.match(records[0].errors[0], /network error/);
});

test("cancelling with an AbortSignal stops the run and aborts the calls on the server", async () => {
  await withApi({ latencyMs: 400 }, async ({ api, client, dir }) => {
    const ctl = new AbortController();
    const run = runIntake({ file: SAMPLE, out: join(dir, "p.ndjson"), client, concurrency: 4, useCache: false, signal: ctl.signal });
    await eventually(() => api.stats.inFlight === 4);    // four lookups are really running on the server
    ctl.abort(new Error("interrupted"));
    await assert.rejects(run);
    await eventually(() => api.stats.aborted === 4);
  });
});
