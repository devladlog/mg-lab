import type { Email, RequestId } from "./brand.js";
import { POLICY, STATE_LABEL, priorityFor } from "./policy.js";
import type { NewRequest, ProjectRequest, RequestState } from "./request.js";
import { err, ok, type Result } from "./result.js";

/** Called in the `default` branch: if a case is missing, `state` is not `never` and this line doesn't compile. */
export function assertNever(value: never): never {
  throw new Error(`Unhandled case: ${JSON.stringify(value)}`);
}

export function createRequest(id: RequestId, input: NewRequest): ProjectRequest {
  return { ...input, id, priority: priorityFor(input.budget), state: { kind: "draft" } };
}

export function submit(request: ProjectRequest, now: Date): Result<ProjectRequest, string> {
  if (request.state.kind !== "draft") return err(`Only drafts can be submitted (this one is ${request.state.kind}).`);
  return ok({ ...request, state: { kind: "submitted", submittedAt: now } });
}

export type Decision =
  | { readonly kind: "approve"; readonly by: Email }
  | { readonly kind: "reject"; readonly by: Email; readonly reason: string };

export function decide(request: ProjectRequest, decision: Decision, now: Date): Result<ProjectRequest, string> {
  if (request.state.kind !== "submitted") return err("Only submitted requests can be decided.");
  if (decision.by === request.requestedBy) return err("You can't decide your own request.");

  switch (decision.kind) {
    case "approve":
      return ok({ ...request, state: { kind: "approved", approvedBy: decision.by, approvedAt: now } });
    case "reject":
      if (decision.reason.trim() === "") return err("A rejection needs a reason.");
      return ok({ ...request, state: { kind: "rejected", rejectedBy: decision.by, reason: decision.reason.trim() } });
    default:
      return assertNever(decision);
  }
}

/** Exhaustive by construction: every state is handled, or the build fails. */
export function describe(state: RequestState): string {
  switch (state.kind) {
    case "draft":
      return STATE_LABEL.draft;
    case "submitted":
      return `${STATE_LABEL.submitted} since ${state.submittedAt.toISOString().slice(0, 10)}`;
    case "approved":
      return `${STATE_LABEL.approved} by ${state.approvedBy}`;
    case "rejected":
      return `${STATE_LABEL.rejected} by ${state.rejectedBy}: ${state.reason}`;
    default:
      return assertNever(state);
  }
}

export function summary(request: ProjectRequest): string {
  const amount = request.budget.toLocaleString("en-US");
  return `${request.id}  ${request.priority.padEnd(8)} ${amount.padStart(9)} ${POLICY.currency}  ${request.title}`;
}
