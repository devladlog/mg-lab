import { RowError } from "#src/errors.js";

export const POLICY = Object.freeze({ highFromCents: 5_000_000, boardFromCents: 25_000_000 });

const CODE = /^PR-\d{4}-\d{4}$/;

function parseBudgetCents(text) {
  const clean = text.replaceAll(",", "");
  if (!/^-?\d+(\.\d{1,2})?$/.test(clean)) return undefined;
  return Math.round(Number(clean) * 100);
}

function isRealDate(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return false;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.toISOString().startsWith(text);
}

export function priorityFor(cents) {
  if (cents >= POLICY.boardFromCents) return "Board";
  if (cents >= POLICY.highFromCents) return "High";
  return "Standard";
}

/**
 * Validate one raw record. Collects every problem instead of stopping at the first one.
 * @returns {{ ok: true, request: object } | { ok: false, errors: RowError[] }}
 */
export function validateRow({ row, record }) {
  const errors = [];
  const code = record.code ?? "";
  if (!CODE.test(code)) errors.push(new RowError(row, "code", `"${code}" does not look like PR-YYYY-NNNN`));

  const title = (record.title ?? "").trim();
  if (title === "") errors.push(new RowError(row, "title", "is required"));

  const department = (record.department ?? "").trim();
  if (department === "") errors.push(new RowError(row, "department", "is required"));

  const cents = parseBudgetCents(record.budget ?? "");
  if (cents === undefined) errors.push(new RowError(row, "budget", `"${record.budget}" is not a number`));
  else if (cents <= 0) errors.push(new RowError(row, "budget", "must be greater than zero"));

  if (!isRealDate(record.submitted ?? "")) errors.push(new RowError(row, "submitted", `"${record.submitted}" is not a real date`));

  if (errors.length > 0) return { ok: false, errors };
  return {
    ok: true,
    request: { row, code, title, department, budgetCents: cents, priority: priorityFor(cents), submitted: record.submitted },
  };
}
