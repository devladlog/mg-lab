import { toEmail, toEuros } from "./brand.js";
import { needsJustification } from "./policy.js";
import type { FieldError, NewRequest } from "./request.js";
import { err, ok, type Result } from "./result.js";

/** Narrow `unknown` to a plain object without a cast. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Parse, don't validate: the input is `unknown` (JSON from a file, an HTTP body...), the output is
 * either a fully typed NewRequest or the complete list of problems. Never `any`, never `as NewRequest`.
 */
export function parseNewRequest(input: unknown): Result<NewRequest, FieldError[]> {
  if (!isRecord(input)) return err([{ field: "(body)", message: "Expected a JSON object." }]);

  const errors: FieldError[] = [];
  const fail = (field: string, message: string): void => {
    errors.push({ field, message });
  };

  const { title, budget, requestedBy, justification } = input;

  const cleanTitle = typeof title === "string" ? title.trim() : "";
  if (cleanTitle.length < 3 || cleanTitle.length > 120) fail("title", "Title must be 3 to 120 characters.");

  const euros = typeof budget === "number" ? toEuros(budget) : err("Budget must be a number.");
  if (!euros.ok) fail("budget", euros.error);

  const email = typeof requestedBy === "string" ? toEmail(requestedBy) : err("requestedBy is required.");
  if (!email.ok) fail("requestedBy", email.error);

  if (justification !== undefined && typeof justification !== "string") {
    fail("justification", "Justification must be text.");
  }
  const cleanJustification = typeof justification === "string" ? justification.trim() : "";
  if (euros.ok && needsJustification(euros.value) && cleanJustification.length < 20) {
    fail("justification", "Budgets of 250,000 euros or more need a justification (20+ characters).");
  }

  if (!euros.ok || !email.ok || errors.length > 0) return err(errors);

  // exactOptionalPropertyTypes: we may omit `justification`, but we may not set it to undefined.
  return ok({
    title: cleanTitle,
    budget: euros.value,
    requestedBy: email.value,
    ...(cleanJustification !== "" && { justification: cleanJustification }),
  });
}
