// Code that "works" in plain JavaScript. Every marked line is a real bug the compiler settings catch.
// Run: npm run demo:errors   (expected to fail - tests/strict-flags.test.ts checks the exact errors)
import { Euros } from "../src/brand.js"; // TS1484 verbatimModuleSyntax: a type must be imported with `import type`
import type { RequestState } from "../src/request.js";

const approvers: Record<string, string> = { finance: "sam.demo@contoso.com" };

export function approverFor(department: string): string {
  return approvers[department].toUpperCase(); // TS2532 noUncheckedIndexedAccess: the entry may be undefined
}

interface Draft {
  title: string;
  justification?: string;
}
export const draft: Draft = { title: "CRM", justification: undefined }; // TS2375 exactOptionalPropertyTypes

export function total(items) { // TS7006 strict (noImplicitAny): items is implicitly any
  return items.reduce((sum, i) => sum + i.budget, 0);
}

export function badge(state: RequestState): string {
  switch (state.kind) {
    case "draft":
      return "grey";
    case "submitted":
      return "blue";
    case "approved":
      return "green";
    default:
      return assertNever(state); // TS2345 we forgot "rejected": state is not `never` here
  }
}

function assertNever(value: never): never {
  throw new Error(String(value));
}

export const budget: Euros = 75_000; // TS2322 a raw number is not Euros

export enum Priority { Standard, High } // TS1294 erasableSyntaxOnly: enums generate code, Node can't just strip them
