# DEVLADLOG Code #1 — TypeScript best practices, enforced by the compiler

A small **project request intake** in TypeScript where every "best practice" is something a tool enforces, not a
wiki page:

- **`tsconfig.json` beyond `strict`**: `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
  `verbatimModuleSyntax`, `erasableSyntaxOnly` (none of these are part of the `strict` family)
- **`unknown` at the boundary** + a parser that returns a **`Result<T, E>`** with *all* field errors — no `any`, no `as`
- **Branded types** (`Euros`, `Email`, `RequestId`): a raw `number` is not a budget until it went through `toEuros()`
- **Discriminated union** for the request state + **`assertNever`**: forget a case and the build fails
- **`as const satisfies`** for the policy, and `satisfies Record<State, string>` for labels
- **typescript-eslint `strictTypeChecked`**: floating promises, non-exhaustive switches, non-null assertions
- **Vitest** tests, including tests that prove the demo files fail *for the reasons the video says*
- **TypeScript 7.0 (native) for `tsc`, TypeScript 6.0 for the tools** that need the compiler API

Business rules (same family as the other DEVLADLOG/MG Lab episodes): budget `>= 50,000` is High priority,
`>= 250,000` needs a justification, and you can't decide your own request.

| Path | What it is |
|---|---|
| [`package.json`](package.json) | Scripts (`typecheck`, `lint`, `test`, `build`, `ci`, demos) and the TS 7 / TS 6 side-by-side aliases |
| [`tsconfig.json`](tsconfig.json) / [`tsconfig.build.json`](tsconfig.build.json) | Type-check `src` + `tests` (no emit) / emit `src` to `dist/` |
| [`eslint.config.mjs`](eslint.config.mjs) | Flat config, `defineConfig`, `strictTypeChecked` + `stylisticTypeChecked`, project service |
| [`src/result.ts`](src/result.ts) | `Result<T, E>`, `ok`, `err`, `map` |
| [`src/brand.ts`](src/brand.ts) | `Brand<T, Name>`, `Euros`, `Email`, `RequestId` and their smart constructors |
| [`src/policy.ts`](src/policy.ts) | `POLICY` (`as const satisfies`), `priorityFor`, `STATE_LABEL` (`satisfies Record<...>`) |
| [`src/request.ts`](src/request.ts) | `NewRequest`, the `RequestState` discriminated union, `ProjectRequest` |
| [`src/parse.ts`](src/parse.ts) | `parseNewRequest(input: unknown): Result<NewRequest, FieldError[]>` |
| [`src/workflow.ts`](src/workflow.ts) | `createRequest`, `submit`, `decide`, exhaustive `describe`, `assertNever` |
| [`src/intake.ts`](src/intake.ts) / [`src/cli.ts`](src/cli.ts) | Pure batch intake / the CLI that reads a JSON file |
| [`samples/requests.json`](samples/requests.json) | Five fictional requests (3 valid, 2 invalid) |
| [`tests/`](tests) | 40 Vitest tests (brands, parser, state machine, intake, strict-flag demos) |
| [`demo/unsafe.ts`](demo/unsafe.ts) | Code that is wrong on purpose: 7 different compiler errors from the settings above |
| [`demo/lint-me.ts`](demo/lint-me.ts) | Type-correct code that is still wrong: 3 ESLint errors |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of `npm run ci`, the CLI and both demos |

## Build, test, run

```bash
npm ci --no-audit --no-fund
npm run ci                                   # typecheck (TS 7) + lint + 40 tests + build
npm run intake -- samples/requests.json      # 3 accepted, 2 rejected (exit code 1)
npm run demo:errors                          # expected to FAIL: TS1484, TS2532, TS2375, TS7006, TS2345, TS2322, TS1294
npm run demo:lint                            # expected to FAIL: no-floating-promises, switch-exhaustiveness-check, no-non-null-assertion
npm run typecheck:6                          # same check with TypeScript 6.0 (tsc6)
```

Result here: `npx vitest run` → **Test Files 5 passed, Tests 40 passed**. `tsc` (7.0.2) and `tsc6` (6.0.3) both
type-check clean; ESLint 10.15 + typescript-eslint 8.73 clean. Tested on Node 22.23 / Linux, no cloud resources.

## What we learned / gotchas

- **TypeScript 7.0 has no compiler API, so typescript-eslint can't use it.** `require("typescript")` on 7.0.2 returns
  only `{ version, versionMajorMinor }`, and typescript-eslint 8.73 declares `typescript >=4.8.4 <6.1.0` as its peer.
  The TypeScript team's answer is to run both: `"@typescript/native": "npm:typescript@^7.0.2"` (gives you `tsc`) and
  `"typescript": "npm:@typescript/typescript6@^6.0.2"` (gives tools the 6.0 API and a `tsc6` command).
- **`@types/node` was installed and `process` was still unknown.** Since TypeScript 6.0, `types` defaults to `[]`,
  so nothing from `node_modules/@types` is loaded automatically. Without `"types": ["node"]` our CLI got TS2591
  *Cannot find name 'process'*.
- **`strict` is not the whole story.** `strict` is on by default now, but `noUncheckedIndexedAccess` and
  `exactOptionalPropertyTypes` are *not* part of it. They caught two of the bugs in `demo/unsafe.ts`.
- **`exactOptionalPropertyTypes` changes how you build objects.** `{ justification: maybeUndefined }` no longer
  compiles; we spread conditionally (`...(text !== "" && { justification: text })`) so the key is absent, and a test
  checks `Object.hasOwn(...)` is false.
- **Node can run `.ts` files, but only erasable syntax.** On Node 22.23 `node file.ts` worked without a flag, and an
  `enum` failed with `ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX ... enum is not supported in strip-only mode`.
  `erasableSyntaxOnly` turns that into compile error TS1294, before it reaches runtime.
- **`noUncheckedIndexedAccess` reports TS2532, not TS18048**, for `record[key].method()` — we had the wrong code in
  the comment until the test that checks the exact errors failed.
- **`tseslint.config()` is deprecated** in favour of ESLint's own `defineConfig()` (from `eslint/config`).
- **`demo/` needs its own `tsconfig.json`**, or the ESLint project service refuses the file ("was not found by the
  project service").

## References
- [JavaScript and TypeScript in Visual Studio — TypeScript 7 native compiler, using TypeScript 6.x per project](https://learn.microsoft.com/visualstudio/javascript/javascript-in-visual-studio)
- [Upgrade the TypeScript compiler (GitHub Copilot upgrade, step through major versions)](https://learn.microsoft.com/dotnet/core/porting/github-copilot-upgrade/javascript-typescript-upgrade-typescript)
- [Transpile TypeScript code using npm](https://learn.microsoft.com/visualstudio/javascript/compile-typescript-code-npm)
- [Announcing TypeScript 7.0 (TypeScript team blog): no API in 7.0, new defaults, side-by-side with 6.0](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/)
- [TSConfig reference (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `erasableSyntaxOnly`)](https://www.typescriptlang.org/tsconfig/)
- [typescript-eslint shared configs (`strictTypeChecked`)](https://typescript-eslint.io/users/configs/)
- Blog: [TypeScript Best Practices — Complete Guide](https://www.devladlog.com/articles/programming-languages/2026-06-07-typescript-best-practices-complete-guide-2026/)
