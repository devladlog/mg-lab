import type { Email, Euros, RequestId } from "./brand.js";
import type { Priority } from "./policy.js";

/** What a requester sends us, after validation. `justification` is truly optional: absent, never `undefined`. */
export interface NewRequest {
  readonly title: string;
  readonly budget: Euros;
  readonly requestedBy: Email;
  readonly justification?: string;
}

/**
 * A discriminated union: `kind` tells the compiler which fields exist.
 * An approved request always has an approver; a draft never does. No optional-field soup.
 */
export type RequestState =
  | { readonly kind: "draft" }
  | { readonly kind: "submitted"; readonly submittedAt: Date }
  | { readonly kind: "approved"; readonly approvedBy: Email; readonly approvedAt: Date }
  | { readonly kind: "rejected"; readonly rejectedBy: Email; readonly reason: string };

export interface ProjectRequest extends NewRequest {
  readonly id: RequestId;
  readonly priority: Priority;
  readonly state: RequestState;
}

export interface FieldError {
  readonly field: string;
  readonly message: string;
}
