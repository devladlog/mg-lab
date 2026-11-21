import { test } from "node:test";
import assert from "node:assert/strict";
import { addDays, daysBetween, defaultDates, loanName, loanState, validateDates } from "../formscripts/loanRules.ts";

const d = (y: number, m: number, day: number) => new Date(y, m - 1, day); // what the form gives for a DateOnly column
const today = d(2026, 11, 21);

test("default loan: today, due in 14 days", () => {
  const r = defaultDates(new Date(2026, 10, 21, 16, 45));
  assert.deepEqual(r, { loanDate: d(2026, 11, 21), dueDate: d(2026, 12, 5) });
});

test("daysBetween counts calendar days across the daylight-saving change", () => {
  process.env.TZ = "Europe/Lisbon"; // clocks go forward on 29 March 2026
  assert.equal(daysBetween(d(2026, 3, 28), d(2026, 3, 30)), 2);
  assert.equal(daysBetween(d(2026, 10, 24), d(2026, 10, 26)), 2); // and back on 25 October
  assert.deepEqual(addDays(d(2026, 3, 28), 2), d(2026, 3, 30));
});

test("valid loan has no errors", () => {
  assert.deepEqual(validateDates({ loanDate: today, dueDate: d(2026, 12, 5), returnedOn: null }, today), []);
});

test("due date before loan date", () => {
  const e = validateDates({ loanDate: today, dueDate: d(2026, 11, 20), returnedOn: null }, today);
  assert.deepEqual(e, [{ field: "contoso_duedate", message: "Due date can't be before the loan date." }]);
});

test("due on the same day is allowed (same-day loan)", () => {
  assert.deepEqual(validateDates({ loanDate: today, dueDate: today, returnedOn: null }, today), []);
});

test("90 days is the limit, 91 is too long", () => {
  assert.deepEqual(validateDates({ loanDate: today, dueDate: addDays(today, 90), returnedOn: null }, today), []);
  const e = validateDates({ loanDate: today, dueDate: addDays(today, 91), returnedOn: null }, today);
  assert.equal(e[0].message, "Loans are limited to 90 days.");
});

test("returned before the loan started", () => {
  const e = validateDates({ loanDate: today, dueDate: d(2026, 12, 5), returnedOn: d(2026, 11, 1) }, today);
  assert.deepEqual(e, [{ field: "contoso_returnedon", message: "Returned on can't be before the loan date." }]);
});

test("returned in the future", () => {
  const e = validateDates({ loanDate: d(2026, 11, 1), dueDate: d(2026, 11, 15), returnedOn: d(2026, 11, 22) }, today);
  assert.equal(e[0].message, "Returned on can't be in the future.");
});

test("missing dates are not errors (required level handles that)", () => {
  assert.deepEqual(validateDates({ loanDate: null, dueDate: null, returnedOn: null }, today), []);
});

test("overdue: one day and several days", () => {
  assert.deepEqual(loanState({ loanDate: d(2026, 11, 1), dueDate: d(2026, 11, 20), returnedOn: null }, today),
    { state: "overdue", days: 1, message: "Overdue by 1 day. Contact the borrower." });
  const s = loanState({ loanDate: d(2026, 11, 1), dueDate: d(2026, 11, 14), returnedOn: null }, today);
  assert.equal(s.state === "overdue" && s.message, "Overdue by 7 days. Contact the borrower.");
});

test("due today and due soon", () => {
  assert.deepEqual(loanState({ loanDate: null, dueDate: today, returnedOn: null }, today), { state: "dueSoon", days: 0, message: "Due today." });
  assert.deepEqual(loanState({ loanDate: null, dueDate: d(2026, 11, 23), returnedOn: null }, today), { state: "dueSoon", days: 2, message: "Due in 2 days." });
  assert.deepEqual(loanState({ loanDate: null, dueDate: d(2026, 11, 24), returnedOn: null }, today), { state: "onTime" });
});

test("returned wins over overdue", () => {
  const s = loanState({ loanDate: d(2026, 10, 1), dueDate: d(2026, 10, 15), returnedOn: d(2026, 11, 2) }, today);
  assert.equal(s.state, "returned");
});

test("loan name", () => {
  assert.equal(loanName("CT-0042 Laptop", "alex.demo@contoso.com", d(2026, 11, 21)), "CT-0042 Laptop - alex.demo - 2026-11-21");
  assert.equal(loanName("x".repeat(120), "a@b.c", today).length, 100);
});
