import { toRequestId } from "./brand.js";
import { parseNewRequest } from "./parse.js";
import type { FieldError, ProjectRequest } from "./request.js";
import { createRequest } from "./workflow.js";

export type IntakeLine =
  | { readonly kind: "accepted"; readonly request: ProjectRequest }
  | { readonly kind: "rejected"; readonly index: number; readonly errors: readonly FieldError[] };

/** Turn a batch of untrusted JSON values into accepted requests and rejections. Pure: no I/O. */
export function intake(batch: readonly unknown[], year: number, firstNumber = 1): IntakeLine[] {
  let next = firstNumber;
  return batch.map((item, index): IntakeLine => {
    const parsed = parseNewRequest(item);
    if (!parsed.ok) return { kind: "rejected", index, errors: parsed.error };

    const id = toRequestId(`PR-${year}-${String(next++).padStart(4, "0")}`);
    if (!id.ok) throw new Error(id.error); // programming error, not user input
    return { kind: "accepted", request: createRequest(id.value, parsed.value) };
  });
}
