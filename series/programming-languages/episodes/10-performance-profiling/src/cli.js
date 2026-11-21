#!/usr/bin/env node
import { parseArgs } from "node:util";
import { bench } from "#src/bench.js";
import { createLruCache, createUnboundedCache, measureCache } from "#src/cache.js";
import { formatHotLines, formatTop, hotLines, loadProfile, summarize } from "#src/cpuprofile.js";
import { generateRequests } from "#src/data.js";
import { measureLoopLag } from "#src/eventloop.js";
import { profileToFile } from "#src/profiler.js";
import { buildReportFast, buildReportSlow } from "#src/report.js";

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    rows: { type: "string", default: "3000" },
    runs: { type: "string", default: "7" },
    out: { type: "string", default: "profiles" },
    keys: { type: "string", default: "150000" },
    json: { type: "boolean", default: false },
  },
});
const [command, arg] = positionals;
const IMPLS = { slow: buildReportSlow, fast: buildReportFast };
const rows = Number(values.rows);

function report(summary, profile) {
  console.log(formatTop(summary, 6));
  console.log();
  console.log(formatHotLines(hotLines(profile), summary.totalMs, 4));
}

switch (command) {
  case "bench": {
    const requests = generateRequests(rows);
    console.log(`${rows} requests, ${values.runs} timed runs after 3 warm-up runs (ms)`);
    for (const [name, fn] of Object.entries(IMPLS)) {
      const s = bench(() => fn(requests), { warmup: 3, runs: Number(values.runs) });
      console.log(`${name.padEnd(5)} median ${s.medianMs.toFixed(1).padStart(8)}   min ${s.minMs.toFixed(1).padStart(8)}   p95 ${s.p95Ms.toFixed(1).padStart(8)}`);
    }
    break;
  }
  case "profile": {
    const build = IMPLS[arg];
    if (!build) { console.error("usage: cli.js profile <slow|fast> [--rows N] [--out DIR]"); process.exitCode = 2; break; }
    const requests = generateRequests(rows);
    const file = `${values.out}/${arg}.cpuprofile`;
    const { profile } = await profileToFile(() => build(requests), file);
    console.log(`${arg}: ${rows} requests -> ${file}`);
    report(summarize(profile), profile);
    break;
  }
  case "top": {
    if (!arg) { console.error("usage: cli.js top <file.cpuprofile>"); process.exitCode = 2; break; }
    const profile = await loadProfile(arg);
    report(summarize(profile), profile);
    break;
  }
  case "lag": {
    const build = IMPLS[arg];
    if (!build) { console.error("usage: cli.js lag <slow|fast> [--rows N]"); process.exitCode = 2; break; }
    const requests = generateRequests(rows);
    const lag = await measureLoopLag(() => build(requests));
    console.log(`${arg}: ${rows} requests built in ${lag.workMs.toFixed(0)} ms; event loop delay max ${lag.maxMs.toFixed(0)} ms, p99 ${lag.p99Ms.toFixed(0)} ms, mean ${lag.meanMs.toFixed(0)} ms (timer every ${lag.resolutionMs} ms)`);
    break;
  }
  case "memory": {
    const keys = Number(values.keys);
    const unbounded = measureCache(createUnboundedCache(), keys);
    const lru = measureCache(createLruCache(1000), keys);
    if (values.json) console.log(JSON.stringify({ keys, unbounded, lru }));
    else {
      console.log(`${keys} distinct keys through each cache (heap in use after a forced collection)`);
      console.log(`unbounded: ${unbounded.entries} entries, +${unbounded.growthMb.toFixed(1)} MB`);
      console.log(`lru(1000): ${lru.entries} entries, +${lru.growthMb.toFixed(1)} MB`);
    }
    break;
  }
  default:
    console.error("usage: cli.js bench | profile <slow|fast> | top <file> | lag <slow|fast> | memory   (options: --rows --runs --out --keys)");
    process.exitCode = 2;
}
