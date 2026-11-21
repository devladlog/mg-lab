import { test } from "node:test";
import assert from "node:assert/strict";
import { setTimeout as sleep } from "node:timers/promises";
import { mapLimit } from "#src/pool.js";
import { createPromiseCache } from "#src/promise-cache.js";

async function collect(gen) { const out = []; for await (const x of gen) out.push(x); return out; }

test("never more than `limit` calls in flight, and all items are processed", async () => {
  let inFlight = 0, max = 0;
  const out = await collect(mapLimit([...Array(20).keys()], 4, async (n) => {
    max = Math.max(max, ++inFlight);
    await sleep(5);
    inFlight--;
    return n * 2;
  }));
  assert.equal(max, 4);
  assert.deepEqual(out.toSorted((a, b) => a - b), [...Array(20).keys()].map((n) => n * 2));
});

test("results come in completion order, not input order", async () => {
  const delays = [60, 10, 30];
  const out = await collect(mapLimit(delays, 3, async (ms) => { await sleep(ms); return ms; }));
  assert.deepEqual(out, [10, 30, 60]);
});

test("the source is pulled lazily: a limit of 2 reads at most 3 items ahead of the consumer", async () => {
  let pulled = 0;
  async function* source() { for (let i = 0; i < 1000; i++) { pulled++; yield i; } }
  const gen = mapLimit(source(), 2, async (n) => { await sleep(1); return n; });
  await gen.next();
  await gen.return();
  assert.ok(pulled <= 3, `pulled ${pulled}`);
});

test("first error fails the pool, aborts the signal given to running calls and closes the source", async () => {
  let aborted = 0, closed = false;
  async function* source() { try { yield 1; yield 2; yield 3; } finally { closed = true; } }
  const run = collect(mapLimit(source(), 3, async (n, { signal }) => {
    if (n === 1) { await sleep(5); throw new Error("boom"); }
    await sleep(500, undefined, { signal }).catch(() => { aborted++; });
    return n;
  }));
  await assert.rejects(run, { message: "boom" });
  assert.equal(aborted, 2);
  assert.equal(closed, true);
});

test("an aborted caller signal stops the pool with the signal's reason", async () => {
  const ctl = new AbortController();
  const gen = mapLimit([1, 2, 3, 4, 5], 1, async (n) => { if (n === 2) ctl.abort(new Error("stop")); return n; }, { signal: ctl.signal });
  await assert.rejects(collect(gen), { message: "stop" });
});

test("limit must be a whole number of at least 1", async () => {
  await assert.rejects(collect(mapLimit([1], 0, async () => 1)), RangeError);
  await assert.rejects(collect(mapLimit([1], 1.5, async () => 1)), RangeError);
});

test("promise cache: concurrent callers share one call, failures are not cached", async () => {
  let calls = 0;
  const cache = createPromiseCache(async (key) => { calls++; await sleep(5); if (key === "bad" && calls < 3) throw new Error("nope"); return key.toUpperCase(); });
  const [a, b] = await Promise.all([cache.get("it"), cache.get("it")]);
  assert.equal(a, "IT"); assert.equal(b, "IT");
  assert.equal(calls, 1);
  assert.deepEqual(cache.stats, { hits: 1, misses: 1 });
  await assert.rejects(cache.get("bad"), { message: "nope" });
  await sleep(0);                                        // let the cleanup run
  assert.equal(await cache.get("bad"), "BAD");           // second try is a real second call
});
