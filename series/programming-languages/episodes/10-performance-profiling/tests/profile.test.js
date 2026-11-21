import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { formatHotLines, formatTop, hotLines, loadProfile, summarize } from "#src/cpuprofile.js";
import { generateRequests } from "#src/data.js";
import { profileToFile } from "#src/profiler.js";
import { buildReportFast, buildReportSlow } from "#src/report.js";

const REPORT_JS = fileURLToPath(new URL("../src/report.js", import.meta.url));
const lineOf = (needle) => readFileSync(REPORT_JS, "utf8").split("\n").findIndex((l) => l.includes(needle)) + 1;

function frame(id, functionName, line, children = [], positionTicks) {
  return { id, callFrame: { functionName, url: "file:///app/x.js", lineNumber: line - 1, columnNumber: 0, scriptId: "1" }, children, positionTicks };
}

test("summarize on a hand-made profile: self and total time, recursion counted once", () => {
  // root -> main -> work -> work (recursive) ; samples: main x1, work x2, work(inner) x3. Every delta is 1000 us.
  const profile = {
    nodes: [frame(1, "(root)", 1, [2]), frame(2, "main", 10, [3]), frame(3, "work", 20, [4]), frame(4, "work", 20)],
    samples: [2, 3, 3, 4, 4, 4],
    timeDeltas: [1000, 1000, 1000, 1000, 1000, 1000],
  };
  const { rows, totalMs } = summarize(profile);
  assert.equal(totalMs, 6);
  const by = Object.fromEntries(rows.map((r) => [r.name, r]));
  assert.equal(by.main.selfMs, 1);
  assert.equal(by.main.totalMs, 6);
  assert.equal(by.work.selfMs, 5);          // both nodes are the same function (same name and line)
  assert.equal(by.work.totalMs, 5);         // recursion: counted once per sample, not twice
  assert.equal(rows[0].name, "work");       // sorted by self time
  assert.match(formatTop({ rows, totalMs }, 2), /work {2}x\.js:20/);
});

test("hotLines splits a node's time by positionTicks", () => {
  const profile = {
    nodes: [frame(1, "(root)", 1, [2]), frame(2, "main", 10, [], [{ line: 11, ticks: 3 }, { line: 12, ticks: 1 }])],
    samples: [2, 2, 2, 2],
    timeDeltas: [1000, 1000, 1000, 1000],
  };
  const rows = hotLines(profile);
  assert.deepEqual(rows.map((r) => [r.line, r.selfMs]), [[11, 3], [12, 1]]);
});

test("profileToFile writes a valid .cpuprofile and survives a throwing function", async () => {
  const dir = await mkdtemp(join(tmpdir(), "prof-"));
  try {
    const file = join(dir, "nested", "a.cpuprofile");
    const { result, profile } = await profileToFile(() => buildReportFast(generateRequests(300)), file);
    assert.equal(result.lines.length > 200, true);
    const onDisk = JSON.parse(await readFile(file, "utf8"));
    assert.deepEqual(Object.keys(onDisk).sort(), ["endTime", "nodes", "samples", "startTime", "timeDeltas"]);
    assert.equal(onDisk.samples.length, onDisk.timeDeltas.length);
    assert.ok(profile.nodes.length > 1);

    await assert.rejects(profileToFile(() => { throw new Error("boom"); }, join(dir, "b.cpuprofile")), { message: "boom" });
    await profileToFile(() => 1, join(dir, "c.cpuprofile"));       // the profiler is not stuck "running"
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test("the profile of the slow report points at the two guilty lines; the fast one is much cheaper", async () => {
  const dir = await mkdtemp(join(tmpdir(), "prof-"));
  try {
    const data = generateRequests(2000);
    const slowFile = join(dir, "slow.cpuprofile");
    await profileToFile(() => buildReportSlow(data), slowFile);
    const slow = await loadProfile(slowFile);
    const summary = summarize(slow);
    const top = summary.rows.find((r) => !r.name.startsWith("(") && !r.url.startsWith("node:"));
    assert.equal(top.name, "buildReportSlow");

    const lines = hotLines(slow).filter((r) => r.url.endsWith("report.js"));
    const guilty = new Set([lineOf("request.budget.toLocaleString"), lineOf("seen.some(")]);
    assert.ok(lines.length >= 2);
    assert.ok(guilty.has(lines[0].line) && guilty.has(lines[1].line), `top lines: ${lines.slice(0, 3).map((l) => l.line)} guilty: ${[...guilty]}`);
    assert.match(formatHotLines(lines, summary.totalMs, 2), /toLocaleString|seen\.some/);

    const fast = await profileToFile(() => buildReportFast(data), join(dir, "fast.cpuprofile"));
    assert.ok(summarize(fast.profile).totalMs < summary.totalMs / 3, "the fast version samples far less time");
  } finally { await rm(dir, { recursive: true, force: true }); }
});
