import { describe, expect, it } from "vitest";
import { toEmail, toEuros, toRequestId, type Email, type Euros, type RequestId } from "../src/brand.js";
import { POLICY, STATE_LABEL, priorityFor } from "../src/policy.js";
import type { ProjectRequest } from "../src/request.js";
import type { Result } from "../src/result.js";
import { assertNever, createRequest, decide, describe as describeState, submit } from "../src/workflow.js";

function unwrap<T>(r: Result<T, unknown>): T {
  if (!r.ok) throw new Error(`expected ok, got ${JSON.stringify(r.error)}`);
  return r.value;
}

const euros = (n: number): Euros => unwrap(toEuros(n));
const email = (s: string): Email => unwrap(toEmail(s));
const id: RequestId = unwrap(toRequestId("PR-2026-0001"));
const alex = email("alex.demo@contoso.com");
const sam = email("sam.demo@contoso.com");
const now = new Date("2026-11-21T10:00:00Z");

const draft = (budget = 75_000): ProjectRequest =>
  createRequest(id, { title: "CRM rollout", budget: euros(budget), requestedBy: alex });

describe("priority", () => {
  it("is High from exactly 50,000 (>=)", () => {
    expect(priorityFor(euros(49_999))).toBe("Standard");
    expect(priorityFor(euros(50_000))).toBe("High");
  });

  it("keeps the literal type of the policy values", () => {
    const threshold: 50_000 = POLICY.highPriorityFrom; // compiles only because of `as const`
    expect(threshold).toBe(50_000);
  });
});

describe("state machine", () => {
  it("draft -> submitted -> approved", () => {
    const submitted = unwrap(submit(draft(), now));
    const approved = unwrap(decide(submitted, { kind: "approve", by: sam }, now));
    expect(approved.state).toEqual({ kind: "approved", approvedBy: sam, approvedAt: now });
    expect(describeState(approved.state)).toBe("Approved by sam.demo@contoso.com");
  });

  it("you can't decide your own request", () => {
    const submitted = unwrap(submit(draft(), now));
    expect(decide(submitted, { kind: "approve", by: alex }, now)).toEqual({
      ok: false,
      error: "You can't decide your own request.",
    });
  });

  it("a rejection needs a reason", () => {
    const submitted = unwrap(submit(draft(), now));
    expect(decide(submitted, { kind: "reject", by: sam, reason: " " }, now).ok).toBe(false);
    const rejected = unwrap(decide(submitted, { kind: "reject", by: sam, reason: "No budget this year" }, now));
    expect(describeState(rejected.state)).toBe("Rejected by sam.demo@contoso.com: No budget this year");
  });

  it("only drafts can be submitted, only submitted requests can be decided", () => {
    const submitted = unwrap(submit(draft(), now));
    expect(submit(submitted, now).ok).toBe(false);
    expect(decide(draft(), { kind: "approve", by: sam }, now).ok).toBe(false);
  });

  it("every state has a label and a description", () => {
    expect(Object.keys(STATE_LABEL).sort()).toEqual(["approved", "draft", "rejected", "submitted"]);
    expect(describeState({ kind: "draft" })).toBe("Draft");
    expect(describeState({ kind: "submitted", submittedAt: now })).toBe("Waiting for approval since 2026-11-21");
  });

  it("assertNever throws if reached at runtime (bad data from outside)", () => {
    expect(() => assertNever({ kind: "archived" } as never)).toThrow('Unhandled case: {"kind":"archived"}');
  });

  it("requests are immutable values", () => {
    const original = draft();
    const submitted = unwrap(submit(original, now));
    expect(original.state.kind).toBe("draft");
    expect(submitted).not.toBe(original);
  });
});
