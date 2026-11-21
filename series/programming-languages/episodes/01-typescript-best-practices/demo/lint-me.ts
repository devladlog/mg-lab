// Type-correct code that is still wrong. Run: npm run demo:lint (expected to fail).
import { writeFile } from "node:fs/promises";
import type { RequestState } from "../src/request.js";

export function saveAudit(line: string): void {
  writeFile("audit.log", line); // no-floating-promises: nobody awaits it, errors vanish
}

export function colour(state: RequestState): string {
  switch (state.kind) { // switch-exhaustiveness-check: "rejected" is not handled
    case "draft":
      return "grey";
    case "submitted":
      return "blue";
    case "approved":
      return "green";
  }
  return "unknown";
}

export function isHigh(budget: number | null): boolean {
  return budget! >= 50_000; // no-non-null-assertion: "trust me, it's not null" - until it is
}
