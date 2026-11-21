import { err, ok, type Result } from "./result.js";

/**
 * Branded types: a plain number or string at runtime, a distinct type at compile time.
 * The only way to get a `Euros` or an `Email` is through the smart constructors below,
 * so a value of that type has always been validated.
 */
declare const brand: unique symbol;
export type Brand<T, Name extends string> = T & { readonly [brand]: Name };

export type Euros = Brand<number, "Euros">;
export type Email = Brand<string, "Email">;
export type RequestId = Brand<string, "RequestId">;

export const MAX_BUDGET = 10_000_000;

export function toEuros(amount: number): Result<Euros, string> {
  if (!Number.isSafeInteger(amount)) return err("Budget must be a whole number of euros.");
  if (amount <= 0) return err("Budget must be greater than zero.");
  if (amount > MAX_BUDGET) return err(`Budget can't exceed ${MAX_BUDGET.toLocaleString("en-US")} euros.`);
  return ok(amount as Euros);
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function toEmail(text: string): Result<Email, string> {
  const value = text.trim().toLowerCase();
  return EMAIL.test(value) ? ok(value as Email) : err("Not a valid e-mail address.");
}

const REQUEST_ID = /^PR-\d{4}-\d{4}$/;

export function toRequestId(text: string): Result<RequestId, string> {
  return REQUEST_ID.test(text) ? ok(text as RequestId) : err("Request id must look like PR-2026-0042.");
}
