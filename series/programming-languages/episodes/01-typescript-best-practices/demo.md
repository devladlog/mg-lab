# Demo shot list — DEVLADLOG Code #1 TypeScript best practices

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none: the screens show the real TypeScript compiler, ESLint, Vitest and VS Code on this project |
| Licences / cost | none |
| Recording machine | The Windows lab laptop: Node.js 22.12+, VS Code, a terminal (Git Bash or WSL bash for the `export PS1` / `rm -rf` lines below) opened in the episode folder under a neutral path |

Everything in this folder was built and tested in the container (`npm run ci`: typecheck + lint + **40 tests
passed** + build). **No tenant, no cloud resources, no licences needed**: all four screens are local captures
(terminal and VS Code). Reference output for every terminal screen: [`demo/expected-output.txt`](demo/expected-output.txt).

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Node.js 22.12 or later | `node --version` (tested on 22.23) | free |
| VS Code | any recent version; dark theme; font size ≥ 18 for capture | free |
| Terminal | dark theme, font ≥ 18 pt, window ~120 columns so the ESLint lines don't wrap badly | free |
| Masking | only the terminal prompt / home path (user name, machine name). Use a neutral prompt, e.g. `PS1='$ '` | — |

## Setup
```bash
cd series/programming-languages/episodes/01-typescript-best-practices
npm ci --no-audit --no-fund
export PS1='$ '        # neutral prompt, no user/host on screen
clear
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/demo-errors.jpg`** — *Seven bugs, caught before runtime* (scene `errors`)
   - `npm run demo:errors`
   - Frame must show the error lines for `demo/unsafe.ts`: TS1484 (line 3), TS2532 (9), TS2375 (16), TS7006 (18),
     TS2345 (31), TS2322 (39), TS1294 (41). It's expected to end with a non-zero exit code; don't show `npm ERR`
     noise (the script runs with `-s` in the test, use `npm run -s demo:errors` for a clean capture).

2. **`screens/editor-never.jpg`** — *A forgotten case, found in the editor* (scene `editor`)
   - `code .` → open `demo/unsafe.ts`, scroll to `badge` (lines 22–33).
   - Hover `state` in `assertNever(state)` on line 31 so the tooltip shows *Argument of type '{ readonly kind: "rejected"; … }'
     is not assignable to parameter of type 'never'*. Problems panel open (click the error count in the status bar) with the other errors.
   - VS Code uses its bundled TypeScript unless you pick the workspace version: **TypeScript: Select TypeScript
     Version → Use Workspace Version** (6.0.3). `node_modules/typescript` is the `@typescript/typescript6` wrapper and
     has no `tsserver.js`; the real 6.0.3 is `node_modules/@typescript/old`, so `typescript.tsdk` must point at
     `node_modules/@typescript/old/lib`. The error text is the same in both.
   - Recording kit: `record.json` opens this exactly (`Open-VsCodeScene.ps1`); the take is clicks and hovers only.
   - Mask: the window title bar if it shows the full path with a user name, and the round account picture at the
     bottom of the activity bar. The recorded take shows that picture, so the scene is cropped with
     `crop: [59, 44, 1846, 980]` in script.yaml (title bar and activity bar removed).

3. **`screens/lint.jpg`** — *Type-correct, still wrong: the linter* (scene `lint`)
   - `npm run -s demo:lint`
   - Frame must show the three errors for `demo/lint-me.ts`: `no-floating-promises` (6:3),
     `switch-exhaustiveness-check` "Cases not matched: "rejected"" (10:11), `no-non-null-assertion` (22:10), and
     `✖ 3 problems`. ESLint prints the absolute file path on the first line: crop it or `cd` from a neutral path.

4. **`screens/ci.jpg`** — *One command for the pipeline* (scene `ci`)
   - `clear && npm run ci` then `npm run -s intake -- samples/requests.json`
   - Frame must show: `Test Files 5 passed (5)`, `Tests 40 passed (40)`, the build step, then three `OK` lines
     (PR-2026-0001 High 75,000 EUR, PR-2026-0002 Standard 18,000 EUR, PR-2026-0003 High 300,000 EUR), two `ERR`
     lines and `3 accepted, 2 rejected`. If it doesn't fit, take two captures and use the intake part.
   - Vitest prints the absolute project path after `RUN v5.1.1`: crop or blur it.

Optional B-roll (not in the script): `time npx tsc -p tsconfig.json` vs `time npx tsc6 -p tsconfig.json`. On this
small project we measured ~0.3 s vs ~1.0 s in the container; don't quote it as a benchmark.

## Tear-down
```bash
rm -rf node_modules dist
```
Nothing was created outside the folder.
