# DEVLADLOG Code #6 — Clean code principles, proven (.NET 10)

A real refactoring, not a list of rules. We take a 60-line legacy method that processes the same Contoso project
requests as episodes 1-5 (`RequestProcessor2.Process(string l, bool f)`), and rewrite it as clean code **without
changing what it does**, then prove it:

- **Gates, not opinions**: a global analyzer config turns on CA1502 (cyclomatic complexity, threshold **10** via
  `CodeMetricsConfig.txt`), CA1031 (catching `Exception`), IDE0011 (braces) and IDE0059 (value never used). The
  legacy project opts out (`EnforceCleanCode=false`); `-p:EnforceCleanCode=true` shows the **17 errors** it would get,
  including *"'Process' has a cyclomatic complexity of '19'"*.
- **Golden master first**: before touching the code, record what it does for 20 tricky input lines, in both modes
  (40 lines in `golden/legacy-output.approved.txt`). The clean code must produce the same 40 lines, except changes we
  decide on and list in the test.
- **The clean version**: intention-revealing names, named constants instead of magic numbers, guard clauses instead of
  six levels of nesting, a `Rejection` enum instead of `"ERR3"`, two methods instead of a `bool` flag, no catch-all.
- **One deliberate behaviour change**: the legacy comment says "budget >= 50k is high" but the code says `> 50000`.
  The series rule is `>=`, so line 7 (exactly 50,000) changes from Normal to High: the only 2 of 40 lines that differ.
- **What the master caught**: "improving" the rounding to `MidpointRounding.AwayFromZero` changes line 9
  (10,870 x 1.15 = 12,500.5 becomes 12,501 instead of 12,500). `Math.Round(decimal)` uses banker's rounding by default.
- **What the master couldn't see**: the catch-all turned a `null` line into `"ERR"`, and `ToUpper(CurrentCulture)`
  rejects department `it` under Turkish culture. Both are pinned by unit tests.

| Path | What it is |
|---|---|
| [`Directory.Build.props`](Directory.Build.props) | `net10.0`, nullable, warnings as errors, `latest-recommended`; adds the gates unless `EnforceCleanCode=false` |
| [`cleancode.globalconfig`](cleancode.globalconfig) / [`CodeMetricsConfig.txt`](CodeMetricsConfig.txt) | CA1502, CA1031, IDE0011, IDE0059 as warnings (errors with warnings-as-errors); `CA1502: 10` |
| [`src/Contoso.Requests.Legacy/RequestProcessor2.cs`](src/Contoso.Requests.Legacy/RequestProcessor2.cs) | The "before": nested ifs, one-letter names, magic numbers, a lying comment, a flag argument, `catch (Exception)` |
| [`src/Contoso.Requests.Clean/RequestProcessor.cs`](src/Contoso.Requests.Clean/RequestProcessor.cs) | The "after": guard clauses in the legacy order, `Outcome` = `Routed` or `Rejected(Rejection)` |
| [`src/Contoso.Requests.Clean/ApprovalPolicy.cs`](src/Contoso.Requests.Clean/ApprovalPolicy.cs) | Named thresholds, `PriorityFor`, `ApproversFor`, `WithContingency` (explicit `MidpointRounding.ToEven`) |
| [`src/Contoso.Requests.Clean/RequestFields.cs`](src/Contoso.Requests.Clean/RequestFields.cs) / [`DepartmentManagers.cs`](src/Contoso.Requests.Clean/DepartmentManagers.cs) | Named questions about one line; ordinal case-insensitive department lookup |
| [`src/Contoso.Requests.Clean/LegacyFormat.cs`](src/Contoso.Requests.Clean/LegacyFormat.cs) | Same `OK;...` / `ERRn` output; `Describe` and `DescribeAfterNotifying` replace the `bool f` |
| [`src/Contoso.Requests.Cli/Program.cs`](src/Contoso.Requests.Cli/Program.cs) | Console app used in the video: `process`, `golden`, `compare [--rounding AwayFromZero]` |
| [`samples/requests.csv`](samples/requests.csv) | 20 fictional lines chosen to hit every branch, boundary and quirk (" 75,000 ", `ops`, 12,500.5, ...) |
| [`golden/legacy-output.approved.txt`](golden/legacy-output.approved.txt) | The approved master: generated once from the legacy code with the `golden` command |
| [`tests/Contoso.Requests.Clean.Tests/`](tests/Contoso.Requests.Clean.Tests) | 18 xUnit tests: golden master (5), policy/parsing/format (11), the null and culture gotchas (2) |
| [`demo/expect-errors.sh`](demo/expect-errors.sh) | Builds legacy with the gates (checks the 4 rule IDs), clean with the gates, runs both comparisons |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of the tests, the script and the `process` command |

## Build, test, run

```bash
dotnet test CleanCode.slnx -m:1                                                   # Passed: 18, Failed: 0 (<1 s)
dotnet build src/Contoso.Requests.Legacy -p:EnforceCleanCode=true --no-incremental # 17 errors (on purpose)
dotnet run --project src/Contoso.Requests.Cli -- compare samples/requests.csv      # 38 identical, 2 different
dotnet run --project src/Contoso.Requests.Cli -- compare samples/requests.csv --rounding AwayFromZero  # 36 / 4
dotnet run --project src/Contoso.Requests.Cli -- process samples/requests.csv      # the clean code's own view
dotnet run --project src/Contoso.Requests.Cli -- golden samples/requests.csv       # re-generates the master (only from legacy!)
./demo/expect-errors.sh                                                            # all of the above with ok/FAIL checks (exit 0)
```

Tested here with .NET SDK 10.0.115 on Linux, 5 consecutive green runs. No packages beyond xUnit, no cloud resources.
The golden master is plain text in the repo, so a reviewer sees any behaviour change as a diff.

## What we learned / gotchas

- **The comment lied, and only the master noticed.** `// budget >= 50k is high` sat above `if (b > 50000)`. Reading
  the code you'd "fix" it silently; the golden master turned it into a visible, listed decision (`IntentionalChanges`
  in `GoldenMasterTests`). Refactor first, change behaviour in a separate, named step.
- **`Math.Round(decimal)` is banker's rounding.** The default midpoint convention is `ToEven` (Learn: `Math.Round`).
  With `AwayFromZero`, 12,500.5 becomes 12,501, and the comparison shows 4 differences instead of 2. The clean code
  now says `MidpointRounding.ToEven` out loud, so the next person doesn't "fix" it.
- **The order of checks is behaviour.** Line 18 is a Board budget with no justification *and* an unknown department.
  Legacy answers `ERR4` because it checks the justification first; the natural clean order would say `ERR3`. The
  guard clauses keep the legacy order, and a test says why.
- **A golden master only sees the inputs you give it.** Two differences never show up in the 40 lines: the
  `catch (Exception)` turned a `null` line into `"ERR"` (clean code throws `ArgumentNullException`), and
  `ToUpper(CultureInfo.CurrentCulture)` turns `it` into `İT` under `tr-TR`, so legacy rejects it (clean code uses
  `StringComparer.OrdinalIgnoreCase`). Both are unit tests now.
- **IDE0059 missed one assignment, as documented.** It reported `string r = ""` but not `decimal b = 0`, which is
  overwritten by `TryParse(..., out b)`. Learn lists the limitation: assignments inside `try`/`catch` blocks aren't
  flagged. Analyzers are a floor, not a review.
- **CA1502 and CA1031 are off by default**, even with `AnalysisLevel=latest-recommended` (Learn: "Enabled by default in
  .NET 10: No"). Without the global config, the legacy method builds clean.
- **Why the opt-out works from a props file.** `Directory.Build.props` is imported before the legacy project sets
  `EnforceCleanCode=false`, but MSBuild evaluates all properties before items, so the `ItemGroup Condition` sees the
  project's value, and a command-line `-p:EnforceCleanCode=true` overrides it again. We checked with `-v diag`: the
  global config reaches the clean project's compiler and not the legacy one.
- **Analyzer noise in the tests**: CA1861 (constant array argument) on `Assert.Equal(new[] {...}, ...)`; a collection
  expression fixed it.

## References
- [CA1502: Avoid excessive complexity (default threshold 25, `CodeMetricsConfig.txt`)](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1502)
- [CA1031: Do not catch general exception types](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1031)
- [IDE0011: Add braces](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/style-rules/ide0011) and [IDE0059: Remove unnecessary value assignment (known limitations)](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/style-rules/ide0059)
- [Configuration files for code analysis rules (global AnalyzerConfig, `GlobalAnalyzerConfigFiles`, conditional inclusion)](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/configuration-files)
- [`Math.Round` (rounding to nearest even by default)](https://learn.microsoft.com/dotnet/api/system.math.round)
- Blog: [Clean Code Principles — Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-02-clean-code-principles-complete-guide-2025/)
