import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Proves the demo files fail for exactly the reasons the video claims. If someone loosens
// tsconfig.json or the ESLint config, these tests go red.
const root = fileURLToPath(new URL("..", import.meta.url));
const run = (script: string): string => {
  // npm is npm.cmd on Windows, and Node only starts .cmd files through a shell
  const win = process.platform === "win32";
  const r = spawnSync(win ? "npm.cmd" : "npm", ["run", "-s", script], { cwd: root, encoding: "utf8", shell: win });
  expect(r.status, `${script} should fail`).not.toBe(0);
  return r.stdout + r.stderr;
};

describe("demo/unsafe.ts under the project tsconfig (TypeScript 7)", () => {
  const output = run("demo:errors");
  const codes = [...output.matchAll(/unsafe\.ts\((\d+),\d+\): error (TS\d+)/g)].map((m) => `${m[1] ?? ""}:${m[2] ?? ""}`);

  it.each([
    ["3:TS1484", "verbatimModuleSyntax: type imported as a value"],
    ["9:TS2532", "noUncheckedIndexedAccess: index may be undefined"],
    ["16:TS2375", "exactOptionalPropertyTypes: explicit undefined"],
    ["18:TS7006", "strict: implicit any parameter"],
    ["31:TS2345", "assertNever: missing union case"],
    ["39:TS2322", "brand: raw number is not Euros"],
    ["41:TS1294", "erasableSyntaxOnly: enum is not erasable"],
  ])("reports %s (%s)", (code) => {
    expect(codes).toContain(code);
  });
});

describe("demo/lint-me.ts under the project ESLint rules", () => {
  const output = run("demo:lint");
  it.each(["no-floating-promises", "switch-exhaustiveness-check", "no-non-null-assertion"])("reports %s", (rule) => {
    expect(output).toContain(`@typescript-eslint/${rule}`);
  });
});
