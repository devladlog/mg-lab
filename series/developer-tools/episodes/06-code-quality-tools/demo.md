# Demo shot list — DEVLADLOG Dev Tools #6, Code quality tools

Already real (build machine, 21 Nov 2026): every excerpt and output on screen except the GitHub and VS Code
views: the build that fails with eight diagnostics on one bad file, `dotnet format --verify-no-changes` and
`dotnet format` (all but CA1305 fixed), Ruff 0.16.9 (12 findings, 6 fixed), the coverage gate on a real git
repository (85/93 total, 5/13 changed lines), `dotnet test` (21 passed, 4 skipped) and `pytest` (133 passed).
**Recorded here for the first time:** the workflow on GitHub-hosted runners, the annotations on the pull request
(`::error`/`::warning` are produced and tested; GitHub draws them), VS Code with the recommended extensions.
Status: **needs GitHub and the recording laptop. No Azure, no Microsoft 365 tenant.**

## Lab environment

| What | Details | Cost |
|---|---|---|
| GitHub | The same account as `github.com/devladlog/mg-lab`. One **public** throwaway repo `orders-app-quality-demo`, created and deleted in this episode. A repo environment `production` with the recording account as required reviewer and **no secrets** (it only holds the baseline run's `deploy` job, which is rejected: no Azure is involved). | none (GitHub-hosted runners, public repo) |
| GitHub Packages | Container package `orders-app-quality-demo` in GHCR, created by the baseline run's `publish` job (episode 5's pipeline); deleted at tear-down. | none |
| Recording laptop (Windows 11) | VS Code with `charliermarsh.ruff` and the C# extension from `.vscode/extensions.json` · **.NET SDK 10** · **git** · **GitHub CLI** (`gh auth login`, scopes `repo`, `workflow`, `read:packages`; `delete_repo` and `delete:packages` added at tear-down) · **Python 3** with `pip install ruff==0.16.9` (the version the workflow pins; check `ruff --version`). No Docker on the laptop: the e2e job runs on GitHub's runner. | none |

Keep the owner and repo names lower case (the workflow publishes `ghcr.io/${{ github.repository }}`).

## Setup (off camera, in this order)

```powershell
$owner = "<github-owner>"; $repo = "orders-app-quality-demo"
$mg = "<path-to>\mg-lab\series\developer-tools\episodes\06-code-quality-tools"     # the episode folder

gh repo create "$owner/$repo" --public --description "DEVLADLOG Dev Tools #6 demo (throwaway)"
```

1. GitHub → repo **Settings → Environments → New environment** `production` → **Required reviewers**: the recording
   account. Nothing else (no secrets, no variables).
2. Import the baseline and let its run finish (warm-up, not recorded). Do **not** run `scripts/setup-dev.sh`: it
   installs episode 1's hooks, which refuse commits on `main`.

```powershell
git clone "https://github.com/$owner/$repo.git"; cd $repo
Copy-Item -Recurse -Force "$mg\src\orders-app\*" .
Get-ChildItem -Force .github\workflows            # ci-cd.yml must be there (dot folders included)
git add -A; git commit -m "chore: import orders api"; git push -u origin main
```

   - Run on `main`: guardrails, quality, build-test, e2e, publish green; `deploy` **Waiting** → **Review deployments →
     Reject** (there is no Azure behind it). Note the run time of `quality` and `build-test`.
   - Check the baseline: `quality` green, the build-test summary shows **Coverage: product code 80/80, 100.0**.
3. Prepare the pull request, **in two commits that are pushed one at a time** (the second after the first screen):

```powershell
git switch -c feat/export-orders-csv
$f = "$mg\tests\fixtures"
Copy-Item "$f\OrderExport.bad.cs"    src\Contoso.Orders.Api\OrderExport.cs
Copy-Item "$f\OrderExportTests.cs"   tests\Contoso.Orders.Api.Tests\OrderExportTests.cs
Copy-Item "$f\Discounts.cs"          src\Contoso.Orders.Api\Discounts.cs
Copy-Item "$f\bad_report.py"         tools\bad_report.py
git add -A; git commit -m "feat(orders): export orders as csv"
```

   Don't push or open the PR yet. The title `feat(orders): export orders as csv` is a valid Conventional Commit
   title (episode 1's guardrail checks it).

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `ci-fails` | `screens/ci-fails.jpg` | `git push -u origin feat/export-orders-csv`, `gh pr create --fill`. 1) **Checks** list: `guardrails` green, `quality` **red**, `build-test` **red**, `e2e` skipped (it needs build-test). 2) `quality` job: the `dotnet format --verify-no-changes` step failed with the `error IDE0161 / WHITESPACE ...` lines, **and the Ruff steps below it still ran** and are red. 3) **Files changed** tab: annotations on `OrderExport.cs` (rule IDs, e.g. IDE0161, CA1305) and on `tools/bad_report.py` (`ruff (F401)`, `ruff (S105)` ...). 4) `build-test`: the `dotnet build` step failing with eight diagnostics on `OrderExport.cs`. |
| `local` | `screens/local.jpg` | On the laptop, in the clone, VS Code: open `OrderExport.cs` (squiggles/Problems panel with the same rule IDs, if the C# extension reports them: say so in a note if it doesn't) and `tools/bad_report.py` (Ruff squiggles; **save** and the formatting changes). Then Windows Terminal: `dotnet format --verify-no-changes` (fails), `dotnet format` (prints `Unable to fix CA1305. No associated code fix found.`), `dotnet build` (only CA1305 left), then `ruff check --fix .` → `Found 12 errors (6 fixed, 6 remaining).`, `ruff format .`. |
| `coverage` | `screens/coverage.jpg` | Make the hand fixes, then push the second commit (below). The run: `quality` **green**, `build-test` red **only at the Coverage gate** step. Capture the step output (`| changed lines | 5/13 | 38.5 |`, `Not covered, changed in this PR: ... Discounts.cs lines 7, 9, 12-17`), the run **Summary** (Coverage table) and the PR **Files changed** tab with the warning "Changed line not executed by any test" on `Discounts.cs`. |
| `green` | `screens/green.jpg` | Push the third commit (adds `DiscountTests.cs`). **Checks** list: `guardrails`, `quality`, `build-test`, `e2e` green (`publish`/`deploy` skipped on a PR); run **Summary** with `| changed lines | 13/13 | 100.0 |`. Don't merge (or squash-merge if you want to show the `main` run: it will stop at `deploy` again, reject it). |

Hand fixes between the first and second screen (record them in `local`):

```powershell
# after `dotnet format` and `ruff check --fix` / `ruff format` (they are on screen):
#   OrderExport.cs: add `using System.Globalization;` and pass CultureInfo.InvariantCulture to ToString("N2")
#   tools/bad_report.py: the six findings Ruff left (S105 password, B006 mutable default, SIM108 x2, E712, SIM115)
Copy-Item "$f\bad_report.fixed.py" tools\bad_report.py      # the hand-fixed file, so the take is short
git diff --stat
git add -A; git commit -m "style: apply the quality rules"; git push
```

The second commit leaves exactly one problem: `Discounts.cs` has no test. Check before pushing that
`src\Contoso.Orders.Api\OrderExport.cs` equals `tests\fixtures\OrderExport.fixed.cs` (a test asserts that this is the
end state of the fixes) and that `dotnet build` and `ruff check .` are clean locally.

```powershell
# third commit
Copy-Item "$f\DiscountTests.cs" tests\Contoso.Orders.Api.Tests\DiscountTests.cs
git add -A; git commit -m "test(orders): cover discount codes"; git push
```

## Checks to make during recording (fix README/tests if any differs)
1. The annotations GitHub draws: do the C# errors (from `dotnet build` and from `dotnet format`) appear on the
   lines of `OrderExport.cs` in **Files changed**? setup-dotnet registers the compiler problem matcher, and the line
   shape matches it in a test, but the drawing is recorded here for the first time. Note the exact titles.
2. `ruff check --output-format github` annotations appear on `tools/bad_report.py` (rule code in the title).
3. The `::warning file=...` lines of the coverage gate show on the PR diff (only lines that are part of the diff are
   decorated; all uncovered changed lines are inside it by construction).
4. `fetch-depth: 0` is enough: the gate's `git diff origin/main...HEAD` works on the pull request merge ref. If it
   fails with "unknown revision", note the message: the fix is to fetch the base explicitly.
5. The numbers on screen equal the ones in the script (85/93 and 5/13 after the second commit, 93/93 and 13/13 after
   the third). If the SDK or runner image changes them, update `script.yaml` and the README (tests will say which).
6. Coverage collection with `--collect "Code Coverage;Format=cobertura"` produces a report on the Ubuntu runner (it
   did on Linux x64 here). Learn's Azure Pipelines page only mentions the built-in collector for Windows; note the
   runner image and architecture.
7. VS Code: does the C# extension show the IDE/CA diagnostics for the file (Problems panel)? If not, say what is needed
   (README gotcha) before saying "the editor shows the same findings".
8. Note the run durations of `quality` and `build-test`.

## Masking
- GitHub: the account avatar/menu and the owner name if the recording account isn't the public devladlog account.
- Terminal: the path of the mg-lab checkout (use a short prompt), the `gh auth status` output (never run it on camera).
- VS Code: the account/Settings Sync badge.

## Tear-down
1. `gh auth refresh -s delete:packages,delete_repo`
2. `gh api -X DELETE /user/packages/container/orders-app-quality-demo` (for an organization owner:
   `/orgs/<org>/packages/container/orders-app-quality-demo`).
3. `gh repo delete <owner>/orders-app-quality-demo --yes` (removes the environment, the runs, artifacts and the Actions cache).
4. Remove the local clone; `gh auth refresh -r delete:packages,delete_repo` to drop the extra scopes.
