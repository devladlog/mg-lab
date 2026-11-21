import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { bench, stats } from "#src/bench.js";
import { createLruCache, createUnboundedCache } from "#src/cache.js";
import { measureLoopLag } from "#src/eventloop.js";

const run = (args, options = {}) => spawnSync(process.execPath, args, { encoding: "utf8", ...options });

test("stats: median of odd and even lists, min, p95", () => {
  assert.deepEqual(stats([5, 1, 3]), { runs: 3, minMs: 1, medianMs: 3, p95Ms: 5, maxMs: 5 });
  assert.equal(stats([4, 1, 3, 2]).medianMs, 2.5);
  assert.equal(stats(Array.from({ length: 100 }, (_, i) => i + 1)).p95Ms, 96);
});

test("bench runs warm-up plus timed runs and uses the median, so one slow run does not move it", () => {
  let calls = 0;
  const s = bench(() => { calls++; return calls; }, { warmup: 2, runs: 5 });
  assert.equal(calls, 7);
  assert.equal(s.runs, 5);
  assert.ok(s.minMs <= s.medianMs && s.medianMs <= s.maxMs);
});

test("event loop delay: a synchronous 150 ms loop shows up as a delay of about that size", async () => {
  const busy = () => { const end = performance.now() + 150; while (performance.now() < end); };
  const lag = await measureLoopLag(busy);
  assert.ok(lag.maxMs >= 120, `max ${lag.maxMs} ms`);
  assert.ok(lag.workMs >= 150);
});

test("LRU cache: bounded, evicts the least recently used key, a read refreshes recency", () => {
  const cache = createLruCache(2);
  const make = (k) => `v-${k}`;
  cache.getOrCompute("a", make);
  cache.getOrCompute("b", make);
  cache.getOrCompute("a", make);                 // a is now newer than b
  cache.getOrCompute("c", make);                 // evicts b
  let computed = 0;
  cache.getOrCompute("a", (k) => { computed++; return k; });
  cache.getOrCompute("b", (k) => { computed++; return k; });
  assert.equal(computed, 1);                     // a was still cached, b had been evicted
  assert.equal(cache.size, 2);
  assert.throws(() => createLruCache(0), RangeError);
  const unbounded = createUnboundedCache();
  for (let i = 0; i < 50; i++) unbounded.getOrCompute(i, make);
  assert.equal(unbounded.size, 50);
});

test("memory: after 60,000 distinct keys the unbounded cache holds all of them and megabytes; the LRU holds 1,000 and almost nothing", () => {
  const out = run(["--expose-gc", "src/cli.js", "memory", "--json", "--keys", "60000"]);
  assert.equal(out.status, 0, out.stderr);
  const { unbounded, lru } = JSON.parse(out.stdout);
  assert.equal(unbounded.entries, 60_000);
  assert.equal(lru.entries, 1000);
  assert.ok(unbounded.growthMb > 5, `unbounded +${unbounded.growthMb} MB`);
  assert.ok(lru.growthMb < 3, `lru +${lru.growthMb} MB`);
});

test("CLI: profile writes a file and prints the hot lines; top reads a profile written by node --cpu-prof", async () => {
  const dir = await mkdtemp(join(tmpdir(), "cli-"));
  try {
    const p = run(["src/cli.js", "profile", "slow", "--rows", "1500", "--out", dir]);
    assert.equal(p.status, 0, p.stderr);
    assert.match(p.stdout, /slow: 1500 requests -> .*slow\.cpuprofile/);
    assert.match(p.stdout, /buildReportSlow {2}report\.js:\d+/);
    assert.match(p.stdout, /toLocaleString/);

    const r = run(["--cpu-prof", `--cpu-prof-dir=${dir}`, "src/run-report.js", "slow", "1500"]);
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.stdout, /slow: \d+ lines, \d+ duplicates/);
    const written = (await readdir(dir)).filter((f) => /^CPU\..*\.cpuprofile$/.test(f));
    assert.equal(written.length, 1);
    const t = run(["src/cli.js", "top", join(dir, written[0])]);
    assert.equal(t.status, 0, t.stderr);
    assert.match(t.stdout, /buildReportSlow {2}report\.js:\d+/);
  } finally { await rm(dir, { recursive: true, force: true }); }
});
