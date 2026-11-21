// Form script for the Loan main form. Bundled by esbuild as the global Contoso.LoanForm.
// Register ONE handler in the form designer: OnLoad -> Contoso.LoanForm.onLoad,
// with "Pass execution context as first parameter" checked. onLoad wires the OnChange events itself.
import { defaultDates, loanName, loanState, validateDates, type DateField, type LoanDates } from "./loanRules.ts";

const DATE_FIELDS: DateField[] = ["contoso_loandate", "contoso_duedate", "contoso_returnedon"];
const LOCK_WHEN_RETURNED = ["contoso_equipmentid", "contoso_borroweremail", "contoso_loandate", "contoso_duedate"];
const STATE_NOTIFICATION = "contoso.loan.state";
const FORM_TYPE_CREATE = 1; // XrmEnum.FormType.Create (const enums from @types/xrm aren't available at runtime)

/** Replaceable in tests; the platform always uses the real clock. */
export const clock = { now: (): Date => new Date() };

const dateValue = (fc: Xrm.FormContext, name: string): Date | null =>
  (fc.getAttribute(name) as Xrm.Attributes.DateAttribute | null)?.getValue() ?? null;

function readDates(fc: Xrm.FormContext): LoanDates {
  return {
    loanDate: dateValue(fc, "contoso_loandate"),
    dueDate: dateValue(fc, "contoso_duedate"),
    returnedOn: dateValue(fc, "contoso_returnedon"),
  };
}

export function onLoad(executionContext: Xrm.Events.EventContext): void {
  const fc = executionContext.getFormContext();
  const now = clock.now();

  if (fc.ui.getFormType() === FORM_TYPE_CREATE) {
    const defaults = defaultDates(now);
    const loanDate = fc.getAttribute("contoso_loandate") as Xrm.Attributes.DateAttribute;
    const dueDate = fc.getAttribute("contoso_duedate") as Xrm.Attributes.DateAttribute;
    if (!loanDate.getValue()) loanDate.setValue(defaults.loanDate);
    if (!dueDate.getValue()) dueDate.setValue(defaults.dueDate);
  }

  for (const name of [...DATE_FIELDS, "contoso_equipmentid", "contoso_borroweremail"]) {
    fc.getAttribute(name)?.addOnChange((ctx) => refresh(ctx.getFormContext(), clock.now()));
  }
  refresh(fc, now);
}

/** Re-evaluates every rule; safe to call any number of times. */
export function refresh(fc: Xrm.FormContext, now: Date): void {
  const dates = readDates(fc);

  // 1. Field errors: a control notification blocks Save until it's cleared.
  const errors = validateDates(dates, now);
  for (const field of DATE_FIELDS) {
    const control = fc.getControl(field) as Xrm.Controls.StandardControl | null;
    const error = errors.find((e) => e.field === field);
    if (error) control?.setNotification(error.message, `contoso.dates.${field}`);
    else control?.clearNotification(`contoso.dates.${field}`);
  }

  // 2. Form banner: overdue / due soon / returned. Information only, never blocks Save.
  const state = loanState(dates, now);
  if (state.state === "onTime") fc.ui.clearFormNotification(STATE_NOTIFICATION);
  else fc.ui.setFormNotification(state.message, state.state === "overdue" ? "WARNING" : "INFO", STATE_NOTIFICATION);

  // 3. A returned loan is history: lock the fields that define it.
  for (const name of LOCK_WHEN_RETURNED) {
    (fc.getControl(name) as Xrm.Controls.StandardControl | null)?.setDisabled(state.state === "returned");
  }

  // 4. Fill the primary name when it's empty, so lookups and views read well.
  const nameAttr = fc.getAttribute("contoso_name") as Xrm.Attributes.StringAttribute | null;
  const equipment = (fc.getAttribute("contoso_equipmentid") as Xrm.Attributes.LookupAttribute | null)?.getValue();
  const email = (fc.getAttribute("contoso_borroweremail") as Xrm.Attributes.StringAttribute | null)?.getValue();
  if (nameAttr && !nameAttr.getValue() && equipment?.length && email && dates.loanDate) {
    nameAttr.setValue(loanName(equipment[0].name ?? "Equipment", email, dates.loanDate));
  }
}
