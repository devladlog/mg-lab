import { test } from "node:test";
import assert from "node:assert/strict";
import { generateRequests, seeded } from "#src/data.js";
import { buildReportFast, buildReportSlow, priorityOf } from "#src/report.js";

test("generated data is reproducible and has duplicates", () => {
  assert.deepEqual(generateRequests(500, 7), generateRequests(500, 7));
  assert.notDeepEqual(generateRequests(500, 7), generateRequests(500, 8));
  const codes = generateRequests(2000).map((r) => r.code);
  const duplicates = codes.length - new Set(codes).size;
  assert.ok(duplicates > 10 && duplicates < 100, `duplicates: ${duplicates}`);
  assert.equal(seeded(1)(), seeded(1)());
});

test("slow and fast versions produce exactly the same report (several sizes and seeds)", () => {
  for (const [count, seed] of [[0, 1], [1, 1], [50, 2], [400, 3], [1200, 4]]) {
    const data = generateRequests(count, seed);
    assert.deepEqual(buildReportFast(data), buildReportSlow(data), `count ${count}, seed ${seed}`);
  }
});

test("neither version changes its input", () => {
  const data = generateRequests(300, 5);
  const copy = structuredClone(data);
  buildReportSlow(data);
  buildReportFast(data);
  assert.deepEqual(data, copy);
});

test("report content: first occurrence kept, repeats listed, totals add up, euro text", () => {
  const data = [
    { code: "PR-1", title: "a", department: "IT", budget: 12_000, submitted: "2026-01-01" },
    { code: "PR-2", title: "b", department: "IT", budget: 50_000, submitted: "2026-01-02" },
    { code: "PR-1", title: "again", department: "HR", budget: 999_999, submitted: "2026-01-03" },
    { code: "PR-3", title: "c", department: "HR", budget: 250_000, submitted: "2026-01-04" },
  ];
  for (const build of [buildReportSlow, buildReportFast]) {
    const r = build(data);
    assert.deepEqual(r.duplicates, ["PR-1"]);
    assert.deepEqual(r.lines.map((l) => [l.code, l.priority]), [["PR-1", "Standard"], ["PR-2", "High"], ["PR-3", "Board"]]);
    assert.deepEqual(r.byDepartment, { IT: { count: 2, budget: 62_000 }, HR: { count: 1, budget: 250_000 } });
    assert.match(r.lines[1].budgetText, /^€50,000$/);
  }
  assert.equal(priorityOf(49_999), "Standard");
  assert.equal(priorityOf(250_000), "Board");
});
