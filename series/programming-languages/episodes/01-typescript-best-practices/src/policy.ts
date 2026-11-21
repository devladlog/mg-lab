import type { Euros } from "./brand.js";
import type { RequestState } from "./request.js";

/**
 * `as const` keeps the literal values (50000, not number) and makes the object deeply readonly.
 * `satisfies` checks the shape without widening it: a typo in a key is a compile error,
 * and POLICY.highPriorityFrom still has the type 50000.
 */
export const POLICY = {
  highPriorityFrom: 50_000,
  justificationFrom: 250_000,
  currency: "EUR",
} as const satisfies {
  readonly highPriorityFrom: number;
  readonly justificationFrom: number;
  readonly currency: "EUR";
};

export type Priority = "Standard" | "High";

export const priorityFor = (budget: Euros): Priority =>
  budget >= POLICY.highPriorityFrom ? "High" : "Standard";

export const needsJustification = (budget: Euros): boolean => budget >= POLICY.justificationFrom;

/**
 * One label per state. `satisfies Record<...>` means: add a new state to the union and this
 * object stops compiling until it has a label too.
 */
export const STATE_LABEL = {
  draft: "Draft",
  submitted: "Waiting for approval",
  approved: "Approved",
  rejected: "Rejected",
} as const satisfies Record<RequestState["kind"], string>;
