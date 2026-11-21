# Demo shot list — DEVLADLOG Dev Tools #7, Code review best practices

Already real (build machine, 21 Nov 2026): the review kit (size, description, owners, comments, metrics), the pull request itself (two commits made with
git), its tests (green for the author, red for the reviewer's reproduction, GitHub's "Commit suggestion" applied exactly as GitHub would, green after the
follow-up), the workflow's contract and its three commands run on a real branch. `pytest`: 69 passed; `dotnet test` of the baseline: 21 passed, 4 skipped.
**Recorded here for the first time:** the workflow on GitHub-hosted runners, the review in the GitHub UI, `gh api` against a real repository (comments and metrics).
Status: **needs the recording laptop and GitHub**. No Azure, no lab VMs, no Postman.

## Lab environment

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows, the lab host) | Git for Windows (Git Bash), Python 3, GitHub CLI `gh` signed in as the lab's GitHub account, a browser on GitHub, Windows Terminal. .NET 10 SDK only if you want to show `dotnet test` live (not needed: the workflow doesn't build the app). | none |
| GitHub | The same account as `github.com/devladlog/mg-lab`. One **public** throwaway repo `orders-app-review-demo`, created and deleted in this episode. Hosted runners (free for a public repo). | none |

**One account, no second reviewer.** GitHub's docs: *"Pull request authors cannot approve their own pull requests."* The lab has one GitHub identity (LAB.md), so the review is
a **Comment** review, and nobody approves. The demo says so on camera and doesn't pretend otherwise. The merge isn't blocked because the throwaway repo has no
ruleset; with two people, episode 1's ruleset adds one required approval and code-owner review. Do not create a second GitHub account for this.

## Prepare (off camera)

```bash
# Git Bash on the laptop. EP = the episode folder in your clone of mg-lab
EP=/c/src/mg-lab/series/developer-tools/episodes/07-code-review-best-practices
git config --global user.name "Lab Admin"            # the lab account's commit identity (use the GitHub noreply address)
rm -rf /c/work/orders-app-review-demo && cp -r $EP/src/orders-app /c/work/orders-app-review-demo && cd /c/work/orders-app-review-demo
OWNER=$(gh api user --jq .login)
sed -i "s#@contoso/[a-z-]*#@$OWNER#g" .github/CODEOWNERS        # code owners must be real users or teams with write access
git init -b main && git add -A && git commit -m "chore: baseline (orders API from episode 5)"
gh repo create orders-app-review-demo --public --source=. --push
git switch -c feat/cancel-order
git am $EP/src/review-demo/0001-feat-orders-cancel-an-order.patch
git push -u origin feat/cancel-order
gh pr create --title "feat(orders): cancel an order" --body-file $EP/src/review-demo/pr-body.good.md
```

Notes: `git am` needs a committer identity (set above); the patch's author is the fictional "Alex Demo". Two workflow facts to check on the first run:
`actions/checkout` fetches the whole history for `pr-size` and `review-routing` (`fetch-depth: 0`), and the `pr-description` job doesn't need any.
If a check fails on GitHub but not locally, copy the failing log into README "gotchas" before recording.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/pr-open.jpg` — GitHub · the pull request and its checks**
   - Conversation tab: the title, the four-section description, the *Checks* box with **pr-size**, **pr-description**, **review-routing**, all green.
   - Open the `pr-size` run → *Summary*: `size/S: 31 changed lines in 3 files` and the area table; the `review-routing` summary: `@<owner>` for every file (because the demo's CODEOWNERS now names the account).
   - Then: `gh pr edit 1 --body-file $EP/src/review-demo/pr-body.bad.md` → the **pr-description** check re-runs (the `edited` trigger) and turns red with the four findings. Restore with `--body-file ...pr-body.good.md`; it turns green again.

2. **`screens/review.jpg` — GitHub · Files changed, then the terminal**
   - Quick on camera: Files changed, hover the `order!.Status` line, add a comment `issue (blocking): ...`, click the suggestion button (±) and show the suggestion block.
   - Then post the whole review at once (off camera if you prefer): `python3 $EP/src/review-demo/review-payload.py > review.json && gh api repos/$OWNER/orders-app-review-demo/pulls/1/reviews --input review.json`.
     If the API rejects the multi-line comment, post the review with only single-line comments and add the suggestion by hand in the UI.
   - Show the review in the Conversation tab (seven threads, **Comment** review). Say that approve and request changes are not available to the author.
   - In Windows Terminal: `gh api repos/$OWNER/orders-app-review-demo/pulls/1/comments --paginate > comments.json` then
     `python3 tools/review_kit/cli.py comments comments.json`: the label table and `Blocking (3)`. (Everything in the PR comes from one account, so the author column is the same login.)

3. **`screens/followup.jpg` — GitHub · fix, resolve, merge**
   - Push the author's follow-up commit (it contains the fix the suggestion proposes, plus the status constants and the two new tests):
     `git am $EP/src/review-demo/0002-fix-orders-answer-404-for-an-unknown-order-and-409-w.patch && git push`.
     Optional first, 10 seconds: **Commit suggestion** on the issue thread shows the one-click flow; if you use it, `git pull` before applying the patch and expect a conflict
     in `Program.cs` (the follow-up changes the same lines): resolve by taking the patch's version, or skip the button entirely, as the script does.
   - Checks re-run (`pr-size` now says `size/S: 67 changed lines`, still small). Reply to the three blocking threads (`gh api repos/$OWNER/orders-app-review-demo/pulls/1/comments/<id>/replies -f body='...'` or in the UI), click **Resolve conversation** on each, show *All conversations resolved*.
   - **Squash and merge**, delete the branch. The kit only runs on pull requests, so main gets no run.
   - The reply texts are in `review-comments.json` (ids 108 and 109).

4. **`screens/metrics.jpg` — Windows Terminal · `review_kit metrics`**
   ```bash
   cd /c/work/orders-app-review-demo
   python3 tools/review_kit/cli.py metrics --repo $OWNER/orders-app-review-demo --limit 5
   ```
   - One row: `#1`, the lines, hours to merge, and `Never reviewed by anyone but the author: #1` (the review was a comment by the author's own account, which the tool ignores on purpose).
   - Check the `additions`/`deletions` fields come back from `gh api repos/<o>/<r>/pulls/1` (the docs' example for *Get a pull request* is truncated before them; the tests use fixtures shaped like the documented create example). If `Lines` shows `-`, say nothing about size here and note it in README.

## Mask / on-screen hygiene
- `gh auth status` output and tokens never on screen. The GitHub account name is the public `devladlog` account: fine, mask if the lab account is anything else.
- The patches carry the fictional author `Alex Demo <alex.demo@contoso.example>`; no real names or addresses.

## Tear-down
- `gh repo delete $OWNER/orders-app-review-demo --yes` and `rm -rf /c/work/orders-app-review-demo` (also `comments.json`, `review.json`).
- Nothing was created in Azure, Entra or Microsoft 365.
