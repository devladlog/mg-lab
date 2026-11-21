import { describe, expect, it } from "vitest";
import { parseNewRequest } from "../src/parse.js";

const valid = { title: "CRM rollout", budget: 75_000, requestedBy: "alex.demo@contoso.com" };

describe("parseNewRequest", () => {
  it("returns a typed request for valid input", () => {
    const r = parseNewRequest(valid);
    expect(r).toEqual({ ok: true, value: valid });
  });

  it("omits justification instead of setting it to undefined", () => {
    const r = parseNewRequest({ ...valid, justification: "   " });
    expect(r.ok).toBe(true);
    if (r.ok) expect(Object.hasOwn(r.value, "justification")).toBe(false);
  });

  it("collects every problem, not just the first", () => {
    const r = parseNewRequest({ title: "Ok", budget: "50k", requestedBy: "nope" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.map((e) => e.field)).toEqual(["title", "budget", "requestedBy"]);
  });

  it("requires a justification from 250,000 euros", () => {
    const r = parseNewRequest({ ...valid, budget: 250_000 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toEqual([expect.objectContaining({ field: "justification" })]);
  });

  it("accepts 250,000 with a real justification", () => {
    const r = parseNewRequest({ ...valid, budget: 250_000, justification: "Replaces three legacy warehouses." });
    expect(r.ok).toBe(true);
  });

  it.each([null, 42, "text", [valid]])("rejects a non-object body: %j", (body) => {
    const r = parseNewRequest(body);
    expect(r).toEqual({ ok: false, error: [{ field: "(body)", message: "Expected a JSON object." }] });
  });

  it("rejects a justification that is not text", () => {
    const r = parseNewRequest({ ...valid, justification: 123 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error[0]?.field).toBe("justification");
  });
});
