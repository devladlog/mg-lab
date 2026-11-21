# DEVLADLOG Dev Tools #6 — Code quality tools: rules in the build, not in the review

The orders API from [episode 4](../04-docker-for-developers/), with the pipeline from [episode 5](../05-ci-cd-pipeline-setup/),
gets the quality rules a reviewer shouldn't have to remember: .NET analyzers that fail the build, `dotnet format` and
**Ruff** (Python) as the auto-fixers, one `quality` job in the workflow, and a **coverage gate that looks at the lines
a pull request changed**, not only at the total.

```
 editor ──► .editorconfig + ruff.toml  (VS Code: same findings, format on save)
 build  ──► Directory.Build.props: AnalysisLevel 10.0-recommended, EnforceCodeStyleInBuild, TreatWarningsAsErrors
 local  ──► dotnet format · ruff check --fix · ruff format          (fix)
 PR     ──► quality job:  dotnet format --verify-no-changes · ruff check · ruff format --check      (report only)
            build-test:    analyzers run in `dotnet build`; coverage (Cobertura) → tools/coverage_gate.py
                           total ≥ 90 % and changed lines ≥ 80 %, uncovered changed lines annotated on the diff
```

Episode 5's pipeline (locked restore, SQL Server e2e, GHCR, OIDC deploy) is unchanged and not repeated: `publish` now
also needs `quality`. Episode 1's guardrails and rulesets decide which checks are *required*; this episode adds the
checks themselves.

| Path | What it is |
|---|---|
| [`src/orders-app/Directory.Build.props`](src/orders-app/Directory.Build.props) | `AnalysisLevel` 10.0-recommended, `EnforceCodeStyleInBuild`, `TreatWarningsAsErrors`, `GenerateDocumentationFile` + `NoWarn CS1591` for every project |
| [`src/orders-app/.editorconfig`](src/orders-app/.editorconfig) | Episode 2's editor basics plus the C# rules and severities enforced on build; underscores in test names allowed only under `tests/` |
| [`src/orders-app/ruff.toml`](src/orders-app/ruff.toml) | Ruff for `tools/`: rule families E W F I B UP SIM S, line length 120, two documented ignores and three per-file ignores |
| [`src/orders-app/.github/workflows/ci-cd.yml`](src/orders-app/.github/workflows/ci-cd.yml) | Episode 5's workflow + `quality` job (the Python steps run even when the formatting check failed, so one run shows every finding) + coverage collection and gate in `build-test` (`fetch-depth: 0` so the PR base is in history) |
| [`src/orders-app/tools/coverage_gate.py`](src/orders-app/tools/coverage_gate.py) | Cobertura → total line coverage of `src/` and diff coverage from `git diff --unified=0`; job summary + `::warning file=,line=` annotations; exit code 1 on a gate failure |
| [`src/orders-app/.vscode/`](src/orders-app/.vscode/) | Recommended extensions and settings: Ruff as the Python formatter with fix-all and organize-imports on save |
| `src/orders-app/` (rest) | Episode 5's app. Changes that turning the rules on forced: `OnModelCreating(ModelBuilder modelBuilder)` (CA1725), unused `using`s removed from four test files (IDE0005), the Dockerfile copies `.editorconfig` before the source so the image build checks the same rules, `.ruff_cache/` ignored |
| [`tests/fixtures/`](tests/fixtures/) | The recording's pull request, as files the tests use: `OrderExport.bad.cs` and `bad_report.py` (the bad files), `OrderExport.fixed.cs` and `bad_report.fixed.py` (after the fixes), `OrderExportTests.cs`, `Discounts.cs`, `DiscountTests.cs`; plus setup-dotnet's problem matcher and the pinned actions' `action.yml` files |
| [`tests/`](tests/) | 133 pytest tests (below) |

## Run the tests

```bash
cd series/developer-tools/episodes/06-code-quality-tools
(cd src/orders-app && dotnet test)          # Passed! 21 passed, 4 skipped (the SQL Server tests, no SQL Server here)
(cd src/orders-app && ruff check . && ruff format --check .)    # All checks passed! / 9 files already formatted  (ruff 0.16.9)
python3 -m pytest -q tests                   # 133 passed (~3 min: real builds, restores and a real git repository)
```

Needs .NET SDK 10, `git`, Python 3 with `pytest`, `pyyaml`, `jsonschema`, and `ruff==0.16.9` on the PATH (the Ruff tests
skip when another version is installed, because rule sets differ between versions). Tests that need `dotnet` or `ruff`
skip when it is missing.

| Test file | What it proves |
|---|---|
| `test_analyzers.py` (11) | The workflow's own `dotnet` steps pass on the clean app. A **real bad file** added to a clean copy fails `dotnet build` with exactly eight diagnostics (IDE0005, IDE0161, IDE0040, IDE0051, CS0169, CA2016, IDE0055, CA1305) as errors; `dotnet format --verify-no-changes` reports them without touching the file; `dotnet format` fixes all but CA1305 ("No associated code fix found") and the human fix turns the build green; setup-dotnet's problem-matcher regex turns each build line (and each `dotnet format` line) into an annotation; underscores allowed only in `tests/`; with `GenerateDocumentationFile` off the build stops with the `EnableGenerateDocumentationFile` error; with it on and no `NoWarn`, CS1591 appears; settings live only in `Directory.Build.props` |
| `test_python_quality.py` (6) | Real Ruff 0.16.9: the repo's tools are clean (`check` + `format --check`); the bad file is annotated with 10 distinct rules and the right line; `--fix` reports "Found 12 errors (6 fixed, 6 remaining)" and leaves S105, B006, SIM108, E712, SIM115; `format` is a separate check and a separate fix; VS Code settings parse and match the Ruff extension's documented example |
| `test_coverage_gate.py` (10) | A **real PR in a real git repo** (the recording's, after the style fixes): a branch adds a tested CSV export and `Discounts.cs` without a test; coverage is collected by the workflow's own `dotnet test` command; the total (85/93 lines, 91.4 %) passes while the diff gate fails (5/13 changed lines, 38.5 %) with annotations on `Discounts.cs` lines 7, 9, 12-17; adding the test makes the same command pass (93/93 and 13/13) and the summary is appended per run. Plus unit tests: diff parsing, line ranges, non-coverable lines, wrong `--include`, no report, a folder that doesn't exist, foreign paths |
| `test_workflow.py` (62) | Episode 5's contract tests (schema, pinned SHAs, every `with:` input exists, contexts, permissions, deploy chain) updated for the new graph, plus the `quality` job's exact steps, coverage collection and gate arguments, `publish` needing `quality`, `setup-python` pinned and its inputs checked against its `action.yml` |
| `test_build_and_smoke.py` (9) | Runs every `run:` step of `build-test` in a clean copy, now including `--collect "Code Coverage;Format=cobertura"` and the coverage gate (**100.0 % of the product lines covered**, a Cobertura file is written), then smoke-tests the API it built; lock-file cases from episode 5 |
| `test_e2e_script.py` (7), `test_infra.py` (7), `test_image_inputs.py` (5), `test_tools.py` (11) | Episode 5's script, Bicep, image-context and tool tests, still green with the rules on |
| `test_script.py` (5) | `script.yaml`: header, 16 scenes, word count, 3 shorts, 4 screens; every configuration excerpt on screen is a real line of the real file; the numbers on screen are the ones the other tests assert |

**Not run here (no GitHub, no browser, no VS Code):** the workflow on GitHub-hosted runners, the PR annotations (the
`::warning`/`::error` text is produced and tested; how GitHub draws it is recorded), VS Code showing the squiggles,
the SQL Server e2e job. See [demo.md](demo.md). `actionlint` is not installed here; the contract tests cover our rules.

## Try it (a copy of `src/orders-app` as a git repo)

```bash
dotnet format --verify-no-changes                   # CI mode: report, exit code 2 if anything would change
dotnet format                                        # fix what has a code fix
ruff check --fix . && ruff format .                  # safe fixes + formatting
python3 tools/coverage_gate.py TestResults --include src/ --min-line 90 --diff-base main --min-diff 80
```

## What we learned / gotchas

- **IDE (style) rules don't run in `dotnet build` unless you ask.** Learn: code-style analysis is disabled on
  command-line builds by default; set `EnforceCodeStyleInBuild` and give each rule a severity in `.editorconfig`.
- **IDE0005 (unused using) needs XML documentation on, and the compiler tells you.** With `GenerateDocumentationFile`
  off and the rule set to warning, `dotnet build` stops with `error EnableGenerateDocumentationFile: Set MSBuild
  property 'GenerateDocumentationFile' to 'true' in project file to enable IDE0005 ... on build`. With it on, every
  public member without a doc comment is CS1591, which `TreatWarningsAsErrors` turns into a failure: we add `CS1591`
  to `NoWarn` (both behaviours are tested).
- **Some rules are off or only a suggestion by default.** Learn lists CA1305 as "Enabled by default in .NET 10: No" and
  CA2016 as "As suggestion"; `.editorconfig` raises both to warning, which `TreatWarningsAsErrors` makes an error.
- **`AnalysisLevel` pins the rule set.** `10.0-recommended` is the `<version>-<mode>` form from Learn: the rules that
  shipped with .NET 10, even after a newer SDK adds more.
- **`dotnet format` writes its findings to stderr.** A CI step that captures only stdout sees nothing; the exit code
  (2 here) is the signal. `--verify-no-changes` never edits files (tested). Not every rule has a code fix: after
  `dotnet format` the culture rule CA1305 is the one error left, with "Unable to fix CA1305. No associated code fix
  found." A tool can't know whether you mean the current or the invariant culture (Learn: use the invariant culture for
  values stored or read by software).
- **Turning rules on in an existing repo costs a commit.** Here: one parameter renamed to match the base method
  (CA1725) and unused `using`s in four test files (IDE0005). Do it in its own PR.
- **Ruff `--fix` is safe-fixes only.** The Ruff docs: unsafe fixes can change runtime behaviour or remove comments and
  need `--unsafe-fixes`. On our bad file 6 of 12 findings were fixed and 4 more had hidden unsafe fixes; the hard-coded
  password (S105), the mutable default argument (B006) and the unclosed file (SIM115) are for a person.
  `ruff check` and `ruff format` are separate: a file can pass one and fail the other.
- **Pin Ruff in CI** (`ruff==0.16.9`, the version these tests run):
  a new Ruff release can add rules to a rule family you selected and fail a pipeline nobody touched.
- **Our coverage gate crashed on a missing folder** (found by a test): a path that is neither a file nor a folder
  now gives "no Cobertura report found" and exit code 1 instead of a traceback.
- **Totals hide untested changes.** A PR that adds 13 lines, 8 of them untested, to an 80-line product still shows 91.4 % (and 38.5 % of its own lines covered).
  The gate measures only lines the report lists (comments and braces aren't coverable) and takes the highest hit count
  seen per line, so a line covered by any test counts.
- **Learn's Azure Pipelines page says the built-in coverage collector is for Windows and suggests Coverlet on Linux.**
  `--collect "Code Coverage;Format=cobertura"` did work on Linux x64 here with SDK 10.0.115 (and Learn's
  `dotnet-coverage` page lists dynamic instrumentation on Linux x64); we haven't tried Linux arm64 runners.
- **Which checks block a merge is a ruleset decision** (episode 1): a red `quality` job doesn't stop a merge by itself.

## References
- Blog: [Code Quality Tools — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-09-code-quality-tools-complete-guide-2025/)
- Microsoft Learn, code analysis: [Overview of .NET source code analysis](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/overview) (code-style analysis disabled on command-line builds by default, enable with `EnforceCodeStyleInBuild`) ·
  [MSBuild reference: code analysis properties](https://learn.microsoft.com/dotnet/core/project-sdk/msbuild-props#code-analysis-properties) (`AnalysisLevel` and its `<version>-<mode>` values, `EnforceCodeStyleInBuild`) ·
  [Configuration options for code analysis](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/configuration-options) (`dotnet_diagnostic.<id>.severity`) ·
  [Language rules: option format](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/style-rules/language-rules#option-format) (severity in the option form is respected on build from .NET 9) ·
  [IDE0005](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/style-rules/ide0005) (needs XML documentation to run on build) ·
  [CA1305](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1305) · [CA2016](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca2016)
- Microsoft Learn, tools: [dotnet format](https://learn.microsoft.com/dotnet/core/tools/dotnet-format) (`--verify-no-changes`, `--no-restore`, "may restore, compile, and run analyzers": only run it on trusted code) ·
  [Customize code coverage analysis](https://learn.microsoft.com/visualstudio/test/customizing-code-coverage-analysis) (`--collect "Code Coverage;Format=Cobertura"`) ·
  [dotnet-coverage](https://learn.microsoft.com/dotnet/core/additional-tools/dotnet-coverage) (platforms for dynamic instrumentation) ·
  [Build, test, and deploy .NET Core projects (Azure Pipelines)](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/dotnet-core#collect-code-coverage) (built-in collector on Windows, Coverlet on Linux/macOS)
- Ruff: [The Ruff linter](https://docs.astral.sh/ruff/linter/) (safe vs unsafe fixes, `--unsafe-fixes`) · [ruff-vscode](https://github.com/astral-sh/ruff-vscode) (the `[python]` settings used in `.vscode/settings.json`)
- Actions: [actions/setup-python](https://github.com/actions/setup-python) and [actions/setup-dotnet](https://github.com/actions/setup-dotnet) at the commits in `tests/fixtures/actions/pins.json` (setup-dotnet registers the compiler problem matcher used for annotations)
