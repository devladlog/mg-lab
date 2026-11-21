// A tiny stand-in for the model-driven form (formContext), just enough for loanForm.ts.
export interface FakeForm {
  formContext: Xrm.FormContext;
  executionContext: Xrm.Events.EventContext;
  values: Record<string, unknown>;
  set(name: string, value: unknown): void; // user edit: sets the value and fires OnChange
  controlNotifications: Record<string, string | undefined>;
  formNotification: { message: string; level: string } | undefined;
  disabled: Record<string, boolean>;
}

export function fakeForm(initial: Record<string, unknown>, formType = 2): FakeForm {
  const values: Record<string, unknown> = { ...initial };
  const handlers: Record<string, Array<(ctx: Xrm.Events.EventContext) => void>> = {};
  const controlNotifications: Record<string, string | undefined> = {};
  const disabled: Record<string, boolean> = {};
  const form: FakeForm = {} as FakeForm;

  const attribute = (name: string) =>
    name in values
      ? {
          getValue: () => values[name] ?? null,
          setValue: (v: unknown) => { values[name] = v; },
          addOnChange: (h: (ctx: Xrm.Events.EventContext) => void) => { (handlers[name] ??= []).push(h); },
        }
      : null;

  const control = (name: string) =>
    name in values
      ? {
          setNotification: (message: string) => { controlNotifications[name] = message; return true; },
          clearNotification: () => { controlNotifications[name] = undefined; return true; },
          setDisabled: (d: boolean) => { disabled[name] = d; },
        }
      : null;

  const formContext = {
    getAttribute: attribute,
    getControl: control,
    ui: {
      getFormType: () => formType,
      setFormNotification: (message: string, level: string) => { form.formNotification = { message, level }; return true; },
      clearFormNotification: () => { form.formNotification = undefined; return true; },
    },
  } as unknown as Xrm.FormContext;

  const executionContext = { getFormContext: () => formContext } as unknown as Xrm.Events.EventContext;

  Object.assign(form, {
    formContext,
    executionContext,
    values,
    controlNotifications,
    disabled,
    formNotification: undefined,
    set(name: string, value: unknown) {
      values[name] = value;
      for (const h of handlers[name] ?? []) h(executionContext);
    },
  });
  return form;
}
