import { test } from "node:test";
import assert from "node:assert/strict";
import { clock, onLoad } from "../formscripts/loanForm.ts";
import { fakeForm } from "./fakeForm.ts";

const d = (y: number, m: number, day: number) => new Date(y, m - 1, day);
const now = new Date(2026, 10, 21, 10, 30);
clock.now = () => now;
const blankLoan = () => ({
  contoso_name: null, contoso_equipmentid: null, contoso_borroweremail: null,
  contoso_loandate: null, contoso_duedate: null, contoso_returnedon: null,
});

test("new loan gets today and a due date 14 days out", () => {
  const f = fakeForm(blankLoan(), 1);
  onLoad(f.executionContext);
  assert.deepEqual(f.values.contoso_loandate, d(2026, 11, 21));
  assert.deepEqual(f.values.contoso_duedate, d(2026, 12, 5));
  assert.equal(f.formNotification, undefined);
});

test("existing record: defaults are not applied", () => {
  const f = fakeForm({ ...blankLoan(), contoso_loandate: d(2026, 11, 2), contoso_duedate: d(2026, 11, 30) }, 2);
  onLoad(f.executionContext);
  assert.deepEqual(f.values.contoso_loandate, d(2026, 11, 2));
});

test("picking an earlier due date puts a blocking notification on the field, fixing it clears it", () => {
  const f = fakeForm(blankLoan(), 1);
  onLoad(f.executionContext);
  f.set("contoso_duedate", d(2026, 11, 1));
  assert.equal(f.controlNotifications.contoso_duedate, "Due date can't be before the loan date.");
  f.set("contoso_duedate", d(2026, 11, 28));
  assert.equal(f.controlNotifications.contoso_duedate, undefined);
});

test("overdue loan shows a warning banner on load", () => {
  const f = fakeForm({ ...blankLoan(), contoso_loandate: d(2026, 11, 1), contoso_duedate: d(2026, 11, 18) });
  onLoad(f.executionContext);
  assert.deepEqual(f.formNotification, { message: "Overdue by 3 days. Contact the borrower.", level: "WARNING" });
});

test("returning the device locks the loan and replaces the banner", () => {
  const f = fakeForm({ ...blankLoan(), contoso_equipmentid: [{ id: "{00000000-0000-0000-0000-000000000001}", name: "CT-0042", entityType: "contoso_equipment" }],
    contoso_borroweremail: "alex.demo@contoso.com", contoso_loandate: d(2026, 11, 1), contoso_duedate: d(2026, 11, 18) });
  onLoad(f.executionContext);
  f.set("contoso_returnedon", d(2026, 11, 21));
  assert.equal(f.formNotification?.level, "INFO");
  assert.equal(f.disabled.contoso_duedate, true);
  assert.equal(f.disabled.contoso_equipmentid, true);
  f.set("contoso_returnedon", null); // undo
  assert.equal(f.disabled.contoso_duedate, false);
});

test("name is filled once equipment and borrower are known, and never overwritten", () => {
  const f = fakeForm(blankLoan(), 1);
  onLoad(f.executionContext);
  f.set("contoso_equipmentid", [{ id: "{00000000-0000-0000-0000-000000000001}", name: "CT-0042 Laptop", entityType: "contoso_equipment" }]);
  assert.equal(f.values.contoso_name, null);
  f.set("contoso_borroweremail", "alex.demo@contoso.com");
  assert.equal(f.values.contoso_name, "CT-0042 Laptop - alex.demo - 2026-11-21");
  f.values.contoso_name = "Custom name";
  f.set("contoso_borroweremail", "sam.demo@contoso.com");
  assert.equal(f.values.contoso_name, "Custom name");
});
