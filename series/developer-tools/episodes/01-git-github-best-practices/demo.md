# Demo shot list — DEVLADLOG Dev Tools #1, Git & GitHub best practices

Everything except the four `screen` scenes is already real (code excerpts and test output from this folder,
`python3 -m pytest -q` → 54 passed). No Microsoft tenant is involved. The live part needs **a GitHub account and a
throwaway repository**. Status: **needs GitHub** for `ruleset` and `pr`; `badcommit` and `secret` only need a terminal.

## Prerequisites
- The lab GitHub account (cost: none). Use a **public** throwaway repository: rulesets work on public repos with
  GitHub Free; a private repo needs Pro/Team/Enterprise.
- A second GitHub account or a collaborator to show "Review required" (optional: the screen works without approving).
- Local: Git 2.30+, Python 3.10+, `gh` CLI signed in as the repo admin (`gh auth login`, off camera).
- Terminal: dark theme, font ≥ 18 pt, 1920×1080, prompt shortened (`PS1='$ '`), no username/host in the prompt.

## Setup
```bash
gh repo create guardrails-demo --public --clone      # off camera; repo owner = lab account
cd guardrails-demo
cp -r <mg-lab>/series/developer-tools/episodes/01-git-github-best-practices/src/kit/. .
sed -i 's#@contoso/dev-team#@<lab-account>#; s#@contoso/platform-team#@<lab-account>#; s# @contoso/security##' .github/CODEOWNERS
mkdir -p tests && printf 'def test_smoke():\n    assert True\n' > tests/test_smoke.py   # so the `test` job has something to run
bash scripts/setup-dev.sh
git add . && git commit -m "chore: add repo guardrails" && git push -u origin main

# first PR so the three check names exist, then lock main
git switch -c chore/first-ci && git commit --allow-empty -m "ci: first run" && git push
gh pr create --fill && gh pr checks --watch            # test, secret-scan, pr-title all green
gh pr merge --squash --delete-branch
git switch main && git pull

scripts/configure-repo.sh <lab-account>/guardrails-demo
scripts/apply-ruleset.sh  <lab-account>/guardrails-demo   # → created ruleset <id> protect-main (active)
```
If `configure-repo.sh` reports `delete_branch_on_merge=false`, set it in Settings → General (it doesn't block the demo).

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `badcommit` | `screens/badcommit.jpg` | Terminal: the `setup-dev.sh` line `Hooks: .githooks \| fetch.prune=true pull.ff=only`; `git switch -c feature/orders-paging`; `mkdir -p src && echo 'PAGE_SIZE = 50' > src/orders.py && git add src/orders.py`; `git commit -m "updated stuff"` with the whole rejection (header error, three examples, types line, "Your message is kept…"); then `git commit -m "feat(orders): add paging"` succeeding. |
| `secret` | `screens/secret.jpg` | `cat src/settings.py` with a **fake** token (`python3 -c "import secrets,string;print('GH_TOKEN = \"ghp_'+''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(36))+'\"')" > src/settings.py`), `git add`, `git commit -m "feat: read token"` → `commit blocked / src/settings.py:1: GitHub token`. Then `git restore --staged src/settings.py && rm src/settings.py`, `git switch main`, `touch x && git add x && git commit -m "docs: x"` → "you are on 'main'…". Clean up (`git restore --staged x; rm x`). |
| `ruleset` | `screens/ruleset.jpg` | Browser: repo → Settings → Rules → Rulesets → **protect-main**: Active, target Default branch, Restrict deletions, Block force pushes, Require a pull request (1 approval, code owners, dismiss stale, most recent push approval, conversation resolution, allowed merge methods: Squash), Require status checks `test`, `secret-scan`, `pr-title` (strict). Two captures if it doesn't fit; use the one with the PR + checks sections. |
| `pr` | `screens/pr.jpg` | `git push` the feature branch, `gh pr create --title "updated orders" --body "Paging for orders"`. PR Conversation tab, bottom: `pr-title` failed, `test` + `secret-scan` passed, "Review required", merge disabled, button shows **Squash and merge** only. Second capture (optional, for the narration "goes green"): title edited to `feat(orders): add paging`, re-run the failed job (Checks → Re-run), `pr-title` green, only the review missing. |

Never push the fake-token commit: it's blocked locally anyway, and GitHub push protection for users would also stop
a push to a public repo.

## Masking
- Repo owner/account name in the browser URL bar, breadcrumbs, avatar menu and CODEOWNERS (`pipeline/mask.js`).
- `gh` output that prints `<owner>/guardrails-demo` in the terminal (or crop it out).
- The fake token is random and never real; still blur it in the edit to avoid the look of a leaked secret.
- Author email in any `git log` output: commits are made as the lab identity; set
  `git config user.email alex.demo@contoso.com` and `user.name "Alex Demo"` in the demo repo before recording.

## After recording
- If the real hashes/ids differ from the script, nothing to change: the narration doesn't quote them.
- If the GitHub UI labels differ from the `ruleset` scene narration, adjust the `demo:` text, not the rules.

## Tear-down
1. `gh repo delete <lab-account>/guardrails-demo --yes` (needs the `delete_repo` scope: `gh auth refresh -s delete_repo`).
2. `rm -rf guardrails-demo` locally.
3. Optional: `gh auth logout` on the recording machine.
