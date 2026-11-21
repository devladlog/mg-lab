// Pure loan rules: no Xrm, no DOM, so they run in node --test.
// The date columns use the DateOnly behavior. Learn: for DateOnly, the Client API returns a JavaScript Date at
// midnight in the browser's time zone, so read it with getFullYear/getMonth/getDate (never the UTC getters).

export const DEFAULT_LOAN_DAYS = 14;
export const MAX_LOAN_DAYS = 90;
export const DUE_SOON_DAYS = 2;

export type DateField = "contoso_loandate" | "contoso_duedate" | "contoso_returnedon";

export interface LoanDates {
  loanDate: Date | null;
  dueDate: Date | null;
  returnedOn: Date | null;
}

export interface FieldError {
  field: DateField;
  message: string;
}

/** Calendar day number, immune to daylight-saving changes (a "day" can be 23 or 25 hours long). */
function dayNumber(d: Date): number {
  return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86_400_000;
}

export function daysBetween(from: Date, to: Date): number {
  return dayNumber(to) - dayNumber(from);
}

export function addDays(d: Date, days: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
}

export function dateOnly(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function defaultDates(today: Date): { loanDate: Date; dueDate: Date } {
  const loanDate = dateOnly(today);
  return { loanDate, dueDate: addDays(loanDate, DEFAULT_LOAN_DAYS) };
}

export function validateDates(d: LoanDates, today: Date): FieldError[] {
  const errors: FieldError[] = [];
  if (d.loanDate && d.dueDate) {
    const length = daysBetween(d.loanDate, d.dueDate);
    if (length < 0) errors.push({ field: "contoso_duedate", message: "Due date can't be before the loan date." });
    else if (length > MAX_LOAN_DAYS) errors.push({ field: "contoso_duedate", message: `Loans are limited to ${MAX_LOAN_DAYS} days.` });
  }
  if (d.returnedOn) {
    if (d.loanDate && daysBetween(d.loanDate, d.returnedOn) < 0) {
      errors.push({ field: "contoso_returnedon", message: "Returned on can't be before the loan date." });
    } else if (daysBetween(today, d.returnedOn) > 0) {
      errors.push({ field: "contoso_returnedon", message: "Returned on can't be in the future." });
    }
  }
  return errors;
}

export type LoanState =
  | { state: "returned"; message: string }
  | { state: "overdue"; days: number; message: string }
  | { state: "dueSoon"; days: number; message: string }
  | { state: "onTime" };

export function loanState(d: LoanDates, today: Date): LoanState {
  if (d.returnedOn) return { state: "returned", message: "Returned. The loan is read-only now." };
  if (!d.dueDate) return { state: "onTime" };
  const left = daysBetween(today, d.dueDate);
  if (left < 0) {
    const days = -left;
    return { state: "overdue", days, message: `Overdue by ${days} day${days === 1 ? "" : "s"}. Contact the borrower.` };
  }
  if (left <= DUE_SOON_DAYS) {
    return { state: "dueSoon", days: left, message: left === 0 ? "Due today." : `Due in ${left} day${left === 1 ? "" : "s"}.` };
  }
  return { state: "onTime" };
}

/** "CT-0042 - alex.demo - 2026-11-21": readable in lookups and views. */
export function loanName(equipmentName: string, borrowerEmail: string, loanDate: Date): string {
  const who = borrowerEmail.split("@")[0];
  const y = loanDate.getFullYear();
  const m = String(loanDate.getMonth() + 1).padStart(2, "0");
  const day = String(loanDate.getDate()).padStart(2, "0");
  return `${equipmentName} - ${who} - ${y}-${m}-${day}`.slice(0, 100);
}
