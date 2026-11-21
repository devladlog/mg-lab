// Test harness: runs the COMPILED web resource (dist/*.js) in a fresh VM context with a small fake of the
// slice of the Client API it uses. We test the exact file that gets uploaded, not the TypeScript source.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, "..", "..");           // episode folder
export const CONFIG = JSON.parse(readFileSync(path.join(ROOT, "customization.json"), "utf8"));
export const BUNDLE = path.join(ROOT, CONFIG.webresource.file);

/** Loads the bundle into a new context. `webApi` is the fake Xrm.WebApi. Returns the context (globals). */
export function loadBundle(webApi) {
  const context = vm.createContext({ Xrm: { WebApi: webApi }, encodeURIComponent, console });
  vm.runInContext(readFileSync(BUNDLE, "utf8"), context, { filename: CONFIG.webresource.name });
  return context;
}

/** Resolves "MGL.ProjectRequest.onLoad" against the context, like the form runtime does. */
export function resolveHandler(context, dotted) {
  return dotted.split(".").reduce((obj, key) => (obj == null ? undefined : obj[key]), context);
}

/** A fake Xrm.WebApi that records calls and answers with `entities` or rejects with `error`. */
export function fakeWebApi({ entities = [], error = null } = {}) {
  const calls = [];
  return {
    calls,
    retrieveMultipleRecords(table, options, maxPageSize) {
      calls.push({ table, options, maxPageSize });
      return error ? Promise.reject(error) : Promise.resolve({ entities });
    },
  };
}

/** A fake formContext with attributes, controls, notifications and an onChange registry. */
export function fakeForm({ formType = 2, id = "{00000000-0000-0000-0000-000000000001}", values = {}, controls = null } = {}) {
  const notifications = new Map();
  const onChange = new Map();
  const disabled = new Map();
  const present = controls || Object.keys(values);

  const attribute = (name) => !(name in values) ? null : ({
    getValue: () => values[name],
    setValue: (v) => { values[name] = v; },
    addOnChange: (fn) => { onChange.set(name, [...(onChange.get(name) || []), fn]); },
  });
  const control = (name) => !present.includes(name) ? null : ({
    setDisabled: (d) => disabled.set(name, d),
    getDisabled: () => disabled.get(name) === true,
  });

  const formContext = {
    data: { entity: { getId: () => id } },
    ui: {
      getFormType: () => formType,
      setFormNotification: (message, level, uniqueId) => { notifications.set(uniqueId, { message, level }); return true; },
      clearFormNotification: (uniqueId) => notifications.delete(uniqueId),
    },
    getAttribute: attribute,
    getControl: control,
  };
  const executionContext = { getFormContext: () => formContext };
  /** Simulates the user changing a field: sets the value and fires its OnChange handlers. */
  const change = async (name, value) => {
    values[name] = value;
    for (const fn of onChange.get(name) || []) await fn(executionContext);
  };
  return { formContext, executionContext, notifications, onChange, disabled, change };
}

export const ACCOUNT = [{ id: "{AAAAAAAA-0000-0000-0000-00000000000A}", name: "Contoso Ltd", entityType: "account" }];
