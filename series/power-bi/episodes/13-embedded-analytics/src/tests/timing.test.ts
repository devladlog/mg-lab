import { test } from "node:test";
import assert from "node:assert/strict";
import { msUntilRefresh } from "../client/timing.js";

const now = Date.parse("2026-01-01T10:00:00Z");

test("refreshes five minutes before expiry by default", () => {
  assert.equal(msUntilRefresh("2026-01-01T10:15:00Z", now), 10 * 60 * 1000);
});

test("zero when already inside the margin or in the past", () => {
  assert.equal(msUntilRefresh("2026-01-01T10:04:00Z", now), 0);
  assert.equal(msUntilRefresh("2025-12-31T10:00:00Z", now), 0);
});

test("zero for a value it can't parse, so the page refreshes rather than waits forever", () => {
  assert.equal(msUntilRefresh("tomorrow", now), 0);
});
