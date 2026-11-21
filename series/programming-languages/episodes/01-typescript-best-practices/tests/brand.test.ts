import { describe, expect, expectTypeOf, it } from "vitest";
import { toEmail, toEuros, toRequestId, type Euros } from "../src/brand.js";

describe("toEuros", () => {
  it("accepts a positive whole amount", () => {
    const r = toEuros(75_000);
    expect(r).toEqual({ ok: true, value: 75_000 });
    if (r.ok) expectTypeOf(r.value).toEqualTypeOf<Euros>();
  });

  it.each([
    [0, "greater than zero"],
    [-5, "greater than zero"],
    [12.5, "whole number"],
    [Number.NaN, "whole number"],
    [10_000_001, "can't exceed"],
  ])("rejects %s", (amount, message) => {
    const r = toEuros(amount);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain(message);
  });
});

describe("toEmail", () => {
  it("normalises case and whitespace", () => {
    expect(toEmail("  Alex.Demo@Contoso.com ")).toEqual({ ok: true, value: "alex.demo@contoso.com" });
  });
  it("rejects text without a domain", () => {
    expect(toEmail("alex.demo").ok).toBe(false);
  });
});

describe("toRequestId", () => {
  it("accepts PR-yyyy-nnnn only", () => {
    expect(toRequestId("PR-2026-0042").ok).toBe(true);
    expect(toRequestId("PR-26-42").ok).toBe(false);
  });
});

describe("branding at compile time", () => {
  it("a plain number is not Euros", () => {
    // These lines only type-check because of @ts-expect-error. If the brand stops working, tsc fails.
    // @ts-expect-error a raw number must go through toEuros()
    const raw: Euros = 75_000;
    expect(raw).toBe(75_000);
  });
});
