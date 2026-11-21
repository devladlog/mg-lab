import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

test("demo/gotchas.js prints what the video says it prints", () => {
  const run = spawnSync(process.execPath, ["demo/gotchas.js"], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /after forEach\(async\): saved = 0/);
  assert.match(run.stdout, /a moment later:\s+saved = 3/);
  assert.match(run.stdout, /Promise\.all\(map\):\s+saved = 3/);
  assert.match(run.stdout, /child exit code 1, stderr says "Error: disk full"/);
  assert.match(run.stdout, /error\.cause\.code is "ECONNREFUSED"/);
  assert.match(run.stdout, /iterate at once = 15 lines; after an await = 0 lines, and the loop never finishes/);
  assert.doesNotMatch(run.stdout, /never printed/);
});
