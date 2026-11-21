// Contoso request digest, TypeScript edition.
// Run directly by Node (type stripping): no build step, no bundler. Only erasable syntax is allowed here.

import type { RawRequest } from "./types.ts";

export const HIGH_PRIORITY_CENTS = 5_000_000; // 50,000.00 EUR
export const BOARD_CENTS = 25_000_000; // 250,000.00 EUR
export const BATCH_SIZE = 4;

// A const object plus a union type instead of `enum`: enums are not erasable syntax.
export const Route = { TeamLead: "TeamLead", Finance: "Finance", Board: "Board" } as const;
export type Route = (typeof Route)[keyof typeof Route];

export interface Request {
  readonly code: string;
  readonly title: string;
  readonly department: string;
  readonly cents: number;
}

export type Outcome =
  | { readonly kind: "accepted"; readonly request: Request }
  | { readonly kind: "rejected"; readonly code: string; readonly reason: string };

export interface Digest {
  readonly accepted: readonly Request[];
  readonly rejected: readonly { readonly code: string; readonly reason: string }[];
  readonly totalCents: number;
  readonly highPriority: number;
  readonly routes: Readonly<Record<Route, number>>;
  readonly departments: readonly { readonly department: string; readonly count: number; readonly cents: number }[];
  readonly largest: readonly Request[];
  readonly batches: readonly (readonly string[])[];
}

export function routeFor(cents: number): Route {
  if (cents >= BOARD_CENTS) return Route.Board;
  if (cents >= HIGH_PRIORITY_CENTS) return Route.Finance;
  return Route.TeamLead;
}

// JSON.parse gives doubles. 49999.99 * 100 is 4999999.000000001 in IEEE 754, so round, never truncate.
export function toCents(budget: number): number {
  return Math.round(budget * 100);
}

export function validate(raw: RawRequest): Outcome {
  if (raw.budget <= 0) {
    return { kind: "rejected", code: raw.code, reason: "budget must be greater than zero" };
  }
  return {
    kind: "accepted",
    request: {
      code: raw.code,
      title: raw.title,
      department: raw.department.trim().toUpperCase(),
      cents: toCents(raw.budget),
    },
  };
}

export function chunk<T>(items: readonly T[], size: number): T[][] {
  return Array.from({ length: Math.ceil(items.length / size) }, (_, i) => items.slice(i * size, (i + 1) * size));
}

export function buildDigest(raws: readonly RawRequest[]): Digest {
  const outcomes = raws.map(validate);
  const accepted = outcomes.filter((o) => o.kind === "accepted").map((o) => o.request);
  const rejected = outcomes.filter((o) => o.kind === "rejected").map(({ code, reason }) => ({ code, reason }));

  // Object.groupBy (ES2024): no reduce, no manual Map.
  const byRoute = Object.groupBy(accepted, (r) => routeFor(r.cents));
  const routes: Record<Route, number> = {
    TeamLead: byRoute.TeamLead?.length ?? 0,
    Finance: byRoute.Finance?.length ?? 0,
    Board: byRoute.Board?.length ?? 0,
  };

  // Map.groupBy keeps insertion order; toSorted returns a new array (ES2023).
  const departments = Map.groupBy(accepted, (r) => r.department)
    .entries()
    .map(([department, items]) => ({
      department,
      count: items.length,
      cents: items.reduce((sum, r) => sum + r.cents, 0),
    }))
    .toArray()
    .toSorted((a, b) => b.cents - a.cents || a.department.localeCompare(b.department, "en"));

  // Iterator helpers (ES2025): lazy map/take over a sorted copy.
  const largest = accepted
    .toSorted((a, b) => b.cents - a.cents || a.code.localeCompare(b.code, "en"))
    .values()
    .take(3)
    .toArray();

  return {
    accepted,
    rejected,
    totalCents: accepted.reduce((sum, r) => sum + r.cents, 0),
    highPriority: accepted.filter((r) => r.cents >= HIGH_PRIORITY_CENTS).length,
    routes,
    departments,
    largest,
    batches: chunk(accepted, BATCH_SIZE).map((batch) => batch.map((r) => r.code)),
  };
}

// Integer maths only: 132037075 -> "1,320,370.75".
export function money(cents: number): string {
  const whole = Math.trunc(cents / 100);
  const fraction = String(cents % 100).padStart(2, "0");
  return `${whole.toLocaleString("en-US")}.${fraction}`;
}

export function render(digest: Digest): string {
  const lines = [
    "Contoso request digest",
    `accepted ${digest.accepted.length}, rejected ${digest.rejected.length}, ` +
      `total ${money(digest.totalCents)} EUR, high priority ${digest.highPriority}`,
    "rejected:",
    ...digest.rejected.map((r) => `  ${r.code}  ${r.reason}`),
    "by route:",
    ...Object.values(Route).map((route) => `  ${route.padEnd(9)}${String(digest.routes[route]).padStart(2)}`),
    "by department:",
    ...digest.departments.map(
      (d) => `  ${d.department.padEnd(6)}${String(d.count).padStart(2)}  ${money(d.cents).padStart(13)} EUR`,
    ),
    "largest three:",
    ...digest.largest.map((r, i) => `  ${i + 1}. ${r.code}  ${r.title}  ${money(r.cents)} EUR`),
    `review batches of ${BATCH_SIZE}:`,
    ...digest.batches.map((codes, i) => `  ${i + 1}: ${codes.join(", ")}`),
  ];
  return lines.join("\n") + "\n";
}
