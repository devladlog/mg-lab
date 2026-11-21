import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  buildHeader, checkMessage, DEFAULT_TYPES, MAX_HEADER, normaliseTypes, replaceHeader, validateScope, validateSubject,
} from "../commitRules";

test("buildHeader: type, optional scope, breaking marker", () => {
  assert.equal(buildHeader({ type: "feat", subject: "add paging" }), "feat: add paging");
  assert.equal(buildHeader({ type: "fix", scope: "api", subject: " handle empty file " }), "fix(api): handle empty file");
  assert.equal(buildHeader({ type: "feat", scope: "api", breaking: true, subject: "drop v1" }), "feat(api)!: drop v1");
  assert.equal(buildHeader({ type: "docs", scope: "", subject: "explain hooks" }), "docs: explain hooks");
});

test("validateSubject: accepts a good subject", () => {
  assert.equal(validateSubject({ type: "feat", scope: "orders", subject: "add paging" }), undefined);
});

test("validateSubject: empty, period, capitalised", () => {
  assert.match(validateSubject({ type: "feat", subject: "  " })!, /Describe the change/);
  assert.equal(validateSubject({ type: "feat", subject: "add paging." }), "No period at the end");
  assert.match(validateSubject({ type: "feat", subject: "Added paging" })!, /lower-case verb/);
  assert.equal(validateSubject({ type: "feat", subject: "API paging" }), undefined); // acronyms are fine
});

test("validateSubject: counts the WHOLE header, scope and ! included", () => {
  const room = MAX_HEADER - "feat(orders)!: ".length;
  assert.equal(validateSubject({ type: "feat", scope: "orders", breaking: true, subject: "x".repeat(room) }), undefined);
  assert.equal(
    validateSubject({ type: "feat", scope: "orders", breaking: true, subject: "x".repeat(room + 1) }),
    `Header is ${MAX_HEADER + 1}/${MAX_HEADER} characters: shorten the subject`,
  );
});

test("validateScope", () => {
  assert.equal(validateScope(""), undefined);
  assert.equal(validateScope("orders/export"), undefined);
  assert.ok(validateScope("Orders"));
  assert.ok(validateScope("my scope"));
});

test("checkMessage: same verdicts as the episode 1 hook", () => {
  const valid = [
    "feat: add paging to the orders endpoint",
    "fix(api): handle an empty export file",
    "feat(api)!: drop the v1 orders endpoint",
    "fix: trim names\n\nCustomers pasted names with trailing spaces.",
    "Merge branch 'main' into feature/orders-paging",
    "fixup! feat: add paging",
    "# comment\nfix(ui): keep focus\n\n# ------------------------ >8 ------------------------\ndiff --git a b",
    "fix: trim names\r\n\r\nBody.\r\n",
  ];
  for (const m of valid) assert.ok(checkMessage(m).ok, `${JSON.stringify(m)}: ${checkMessage(m).errors}`);

  const invalid: Array<[string, RegExp]> = [
    ["Updated stuff", /header must look like/],
    ["feat:add paging", /header must look like/],
    ["feature: add paging", /unknown type 'feature'/],
    ["fix: handle empty files.", /period/],
    ["fix: trim\nbody under the header", /blank line/],
    ["", /empty commit message/],
    [`feat: ${"x".repeat(MAX_HEADER)}`, /keep it to 72/],
  ];
  for (const [m, re] of invalid) {
    const r = checkMessage(m);
    assert.equal(r.ok, false, m);
    assert.ok(r.errors.some((e) => re.test(e)), `${m}: ${r.errors}`);
  }
});

test("every header buildHeader produces from valid input passes checkMessage", () => {
  for (const type of DEFAULT_TYPES) {
    for (const scope of ["", "api", "orders/export"]) {
      for (const breaking of [false, true]) {
        const parts = { type, scope, breaking, subject: "add paging" };
        assert.equal(validateSubject(parts), undefined);
        assert.ok(checkMessage(buildHeader(parts)).ok, buildHeader(parts));
      }
    }
  }
});

test("replaceHeader keeps the body the developer already wrote", () => {
  assert.equal(replaceHeader("", "feat: add paging"), "feat: add paging");
  assert.equal(replaceHeader("wip", "feat: add paging"), "feat: add paging");
  assert.equal(
    replaceHeader("wip\n\nUses cursor paging.\nCloses #12", "feat(orders): add paging"),
    "feat(orders): add paging\n\nUses cursor paging.\nCloses #12",
  );
  assert.equal(replaceHeader("old\r\n\r\nBody", "fix: x"), "fix: x\n\nBody");
});

test("normaliseTypes: bad settings fall back to defaults, duplicates removed", () => {
  assert.deepEqual(normaliseTypes(undefined), [...DEFAULT_TYPES]);
  assert.deepEqual(normaliseTypes("feat"), [...DEFAULT_TYPES]);
  assert.deepEqual(normaliseTypes([]), [...DEFAULT_TYPES]);
  assert.deepEqual(normaliseTypes(["feat", "fix", "feat", "Bad", 3]), ["feat", "fix"]);
});
