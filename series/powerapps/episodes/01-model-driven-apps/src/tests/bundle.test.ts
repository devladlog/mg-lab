import { test } from "node:test";
import assert from "node:assert/strict";
import { createContext, runInContext } from "node:vm";
import { buildSync } from "esbuild";

// The form designer calls "Contoso.LoanForm.onLoad" by name: make sure the bundle really exposes it.
test("web resource bundle exposes Contoso.LoanForm.onLoad as a classic (non-module) script", () => {
  const out = buildSync({
    entryPoints: ["formscripts/loanForm.ts"], bundle: true, format: "iife", globalName: "Contoso.LoanForm",
    target: "es2020", write: false,
  });
  const code = out.outputFiles[0].text;
  assert.doesNotMatch(code, /^\s*(import|export)\s/m);
  const sandbox: any = {};
  createContext(sandbox);
  runInContext(code, sandbox);
  assert.equal(typeof sandbox.Contoso.LoanForm.onLoad, "function");
  assert.ok(code.length < 20_000, `bundle is ${code.length} bytes`);
});
