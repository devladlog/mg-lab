# Demo shot list - Copilot & AI #15 GitHub Copilot Coding Agent and Code Review

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** Nothing from the Hyper-V lab (10.50.0.0/24) is used |
| Tenant | Not used. This episode lives on github.com, not in the Microsoft 365 lab tenant |
| GitHub accounts | (1) The owner's GitHub account (the same one that owns the mg-lab repository) as the **requester**. (2) A second GitHub account with **write access** to the throwaway repo, used only to approve the pull request (the requester cannot approve the agent's pull request). If no second account exists, record the first half of the gate only and say so in the narration |
| Licence | **A paid GitHub Copilot plan on the requester account is required** for the cloud agent (GitHub plans page, read 21 Nov 2026: Pro $10, Pro+ $39, Max $100 per month; Business $19 and Enterprise $39 per seat; Free has no cloud agent). **Which plan the owner has is not known: confirm at Settings > Billing and plans > Copilot before recording.** The owner decides whether to buy or trial one; never bought by the builder. If it is a Business/Enterprise organisation account, an admin must enable the cloud agent policy first |
| Cost of the recording | Copilot plan as above (monthly, cancel afterwards) plus GitHub Actions minutes and AI credits used by one or two agent sessions and a few CI runs. Expect a few minutes of Actions time and a small number of credits on a tiny repo; **not verified**, check Billing after the first session |
| Azure | none; no resource group |
| Recording machine | The Windows lab laptop: browser signed in as the requester (dark theme, zoom 125 %), PowerShell 7 or Windows Terminal (dark, 18 pt, window 1600x900), Python 3.10+, .NET 8 SDK, Git, GitHub CLI (`gh`) |
| Tools to install | `python -m pip install -r src/requirements.txt` in the episode folder; `gh auth login` as the requester (off camera, never `pac auth`; the OAuth token it stores is a user-to-server token, which the assignment API accepts) |

## What was verified where

| Step | Verified in the build container (Linux) | Needs GitHub / the owner's plan |
|---|---|---|
| Preflight linters, REST request bodies, gate logic | yes: 59 pytest tests (the `gh` calls against a fake runner) | - |
| Demo repo builds and tests | yes: `dotnet test` 8 passed; with the review patch applied 9 passed | - |
| `copilot-setup-steps.yml` valid by the documented rules | yes: `agent_ready setup-steps` | **run it on GitHub** (Actions tab) |
| Assigning, the agent session, the draft pull request, Approve and run workflows | no | **record it** |
| Copilot code review of the seeded pull request | no | **record it; show whatever Copilot really says** |
| `assign --execute`, `review --execute`, `gate --repo` | no (public-preview API, real token needed) | **first real call** |

If the real service behaves differently from the README (assignee name, check-run conclusion, author login of the
agent's pull request), note it in README "gotchas" and fix the code; do not edit tests to hide it.

## Prerequisites
- `gh auth status` shows the requester. For deleting the repo at the end: `gh auth refresh -s delete_repo`.
- In the requester's Copilot settings, the cloud agent is available (github.com/settings/copilot). On an organisation, the policy is on.
- Terminal prompt shortened: `function prompt { 'PS> ' }`.

## Setup
1. Create the throwaway private repo from the demo folder (the repo content is `src/demo-repo`, nothing else):
   ```powershell
   $T = Join-Path $HOME 'contoso-bikes-pricing'
   Copy-Item .\src\demo-repo $T -Recurse
   Set-Location $T
   Remove-Item -Recurse -Force .\review-demo, .\issues    # these stay in the episode folder, not in the repo
   git init -b main; git add -A; git commit -m "Contoso Bikes pricing baseline"
   gh repo create contoso-bikes-pricing --private --source . --push
   ```
   The patch (`src/demo-repo/review-demo/`) and the issue files (`src/demo-repo/issues/`) are used from the episode folder.
2. Confirm green locally: `dotnet test Contoso.Bikes.sln` -> `8 passed`. Push; confirm the `ci` workflow is green on `main`.
3. Run `python -m agent_ready setup-steps .github/workflows/copilot-setup-steps.yml` (from the episode `src/`, pointing at the repo copy) -> `OK`. In the **Actions** tab run **Copilot Setup Steps** by hand once (`workflow_dispatch`); it must be green. The file is already on `main`, which the docs require.
4. Create the two issues:
   ```powershell
   gh issue create --title "Loyalty price rounds halves to even; finance expects away from zero" --body-file <ready body without the first line>
   ```
   Use the body of `issues/01-...md` without its first (`# title`) line. Issue 2 (vague) is created only if you want the
   "bad issue" shot; do not assign it.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `assign-screen` | `screens/assign-issue.jpg` | Issue 1 in the browser, right sidebar **Assignees > Copilot** selected, the optional prompt box with "Run dotnet test Contoso.Bikes.sln before you finish" typed, the branch and model menus visible. Before this, run `python -m agent_ready issue <issue file>` in the terminal for a second of footage (passes). Mask only the account email |
| `session-screen` | `screens/agent-pr.jpg` | The draft pull request: branch `copilot/...`, commits authored by Copilot (requester as co-author, Verified), the link to the session log, and the merge box with **Approve and run workflows**. Take this before clicking it. Wait time for a task this small is minutes; cut the wait in editing and say so |
| `gate-screen` | `screens/gate-terminal.jpg` | `python -m agent_ready gate --repo <owner>/contoso-bikes-pricing --pull <n> --requested-by <owner login>` twice: (a) draft, no approval, workflows not run -> `WAIT` lines, `Verdict: not ready`; (b) after the second account approved, the pull request was marked ready by a human, and **Approve and run workflows** was clicked and passed -> all `OK`, `Verdict: ready for a human to merge` |
| `review-screen` | `screens/code-review.jpg` | Create the seeded pull request: `git switch -c feature/bulk-discount; git am <path>\0001-add-bulk-discount.patch; git push -u origin feature/bulk-discount; gh pr create --fill`. Request the review (Reviewers > Copilot **Request**, or `python -m agent_ready review <owner>/contoso-bikes-pricing <n> --execute`). Show the real Copilot review (a Comment review with line comments). Do not edit or stage the output. Our four planted problems: `double` for money, `Math.Round` without `MidpointRounding.AwayFromZero`, no validation of negative input, an exception swallowed in `catch`. Say honestly which ones Copilot found |

The `tests-screen` footage for the last code scene is a terminal: `python -m pytest -q` -> `59 passed` and the failing
`agent_ready issue` run on the vague issue.

## Masking notes
- Account emails, access tokens and `gh auth status` token lines never on screen. The tenant is not involved.
- The second reviewer account shows as "Sam Demo" only if its profile is named that; otherwise crop it.

## Tear-down
1. Close or delete the pull requests; delete the branches (`copilot/...`, `feature/bulk-discount`).
2. `gh repo delete <owner>/contoso-bikes-pricing --yes` (needs the `delete_repo` scope), then `Remove-Item -Recurse -Force $HOME/contoso-bikes-pricing`.
3. Remove the second account's collaborator invite if the repo still exists; `gh auth logout` if the laptop is shared.
4. Check Settings > Billing for the Actions minutes and AI credits the recording used and write the figures in the README
   ("What we learned"). Cancel the Copilot plan if it was bought only for this recording.
