import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { BOARD_CENTS, HIGH_PRIORITY_CENTS, Route, buildDigest, chunk, money, render, routeFor, toCents, validate } from "../../src/ts/digest.ts";
import { parseRequests } from "../../src/ts/types.ts";
import type { RawRequest } from "../../src/ts/types.ts";

const root = fileURLToPath(new URL("../../", import.meta.url));
const sample = readFileSync(`${root}samples/requests.json`, "utf8");
// A Windows checkout may turn LF into CRLF: compare text, not line endings.
const golden = readFileSync(`${root}expected/digest.txt`, "utf8").replaceAll("\r\n", "\n");

function raw(over: Partial<RawRequest> = {}): RawRequest {
  return { code: "PR-1", title: "t", department: "IT", budget: 1000, requestedBy: "alex.demo@contoso.com", ...over };
}

describe("routing", () => {
  it("uses the 50,000 and 250,000 boundaries inclusively", () => {
    assert.equal(routeFor(HIGH_PRIORITY_CENTS - 1), Route.TeamLead);
    assert.equal(routeFor(HIGH_PRIORITY_CENTS), Route.Finance);
    assert.equal(routeFor(BOARD_CENTS - 1), Route.Finance);
    assert.equal(routeFor(BOARD_CENTS), Route.Board);
  });
});

describe("money", () => {
  it("rounds instead of truncating floating point budgets", () => {
    assert.equal(toCents(49999.99), 4_999_999);
    assert.equal(toCents(50000.01), 5_000_001);
    assert.equal(Math.trunc(0.29 * 100), 28); // what the naive version would do
    assert.equal(toCents(0.29), 29);
  });
  it("formats cents with grouping and two decimals", () => {
    assert.equal(money(132_037_075), "1,320,370.75");
    assert.equal(money(5), "0.05");
    assert.equal(money(100), "1.00");
  });
});

describe("validate", () => {
  it("rejects zero and negative budgets and normalises the department", () => {
    assert.deepEqual(validate(raw({ code: "PR-9", budget: 0 })), {
      kind: "rejected",
      code: "PR-9",
      reason: "budget must be greater than zero",
    });
    assert.equal(validate(raw({ budget: -5 })).kind, "rejected");
    const ok = validate(raw({ department: " hr " }));
    assert.equal(ok.kind === "accepted" && ok.request.department, "HR");
  });
});

describe("collections", () => {
  it("chunk keeps order and the last batch is short", () => {
    assert.deepEqual(chunk([1, 2, 3, 4, 5, 6, 7, 8, 9], 4), [[1, 2, 3, 4], [5, 6, 7, 8], [9]]);
    assert.deepEqual(chunk([], 4), []);
  });
  it("toSorted does not mutate the source array", () => {
    const original = [3, 1, 2];
    const sorted = original.toSorted();
    assert.deepEqual(original, [3, 1, 2]);
    assert.deepEqual(sorted, [1, 2, 3]);
  });
});

describe("boundary", () => {
  it("parseRequests accepts the sample and names the bad element otherwise", () => {
    assert.equal(parseRequests(sample).length, 13);
    assert.throws(() => parseRequests('[{"code":"x"}]'), /element 0 is not a valid request/);
    assert.throws(() => parseRequests("{}"), /expected a JSON array/);
  });
});

describe("golden file", () => {
  it("the sample digest equals expected/digest.txt", () => {
    assert.equal(render(buildDigest(parseRequests(sample))), golden);
  });
  it("the CLI runs the .ts file directly and prints the same text", () => {
    const out = execFileSync(process.execPath, ["src/ts/main.ts", "samples/requests.json"], { cwd: root, encoding: "utf8" });
    assert.equal(out.replaceAll("\r\n", "\n"), golden);
  });
  it("the CLI exits 2 without arguments", () => {
    const r = spawnSync(process.execPath, ["src/ts/main.ts"], { cwd: root, encoding: "utf8" });
    assert.equal(r.status, 2);
    assert.match(r.stderr, /usage/);
  });
});

describe("type stripping gotcha", () => {
  it("enum is refused by Node with ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX", () => {
    const r = spawnSync(process.execPath, ["demo/ts/uses-enum.ts"], { cwd: root, encoding: "utf8" });
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX/);
  });
});
