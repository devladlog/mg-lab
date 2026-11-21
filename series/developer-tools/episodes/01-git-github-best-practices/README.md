# DEVLADLOG Dev Tools #1 — Git & GitHub best practices, enforced in three layers

A **repo guardrails kit** you copy into any repository. It turns the usual advice (feature branches, pull requests,
a clean `main`, readable history, no secrets in Git) into checks that actually run:

| Layer | When it runs | What it does | Can it be skipped? |
|---|---|---|---|
| **Local hooks** (`.githooks/`) | `git commit` on the developer's machine | Conventional Commit messages, no commits on `main`, no staged secrets, no oversized files | Yes, `--no-verify`. Fast feedback only |
| **CI** (`.github/workflows/ci.yml`) | Every pull request and push to `main` | Tests, secret scan of every tracked file, PR title check | No, it's on the server |
| **Ruleset** (`.github/rulesets/protect-main.json`) | Every push/merge to the default branch | PR required, one approval + code owners, required checks, squash only, no force push or delete | Only by listed bypass actors (none) |

The same Python module (`tools/repo_guard`) backs the hooks and the CI jobs, so the rule a developer sees locally is
exactly the rule the server enforces.

| Path | What it is |
|---|---|
| [`src/kit/tools/repo_guard/commit_rules.py`](src/kit/tools/repo_guard/commit_rules.py) | Conventional Commits 1.0.0 header check (types, scope, `!`, 72-char header, blank line before body) |
| [`src/kit/tools/repo_guard/staged_checks.py`](src/kit/tools/repo_guard/staged_checks.py) | Protected-branch check, size budget and secret patterns, run on the **staged** blobs (`git show :path`) |
| [`src/kit/tools/repo_guard/cli.py`](src/kit/tools/repo_guard/cli.py) | Entry points: hooks, `title "<pr title>"`, `scan-tree` |
| [`src/kit/.githooks/`](src/kit/.githooks/) | `commit-msg` and `pre-commit`, thin wrappers around the module |
| [`src/kit/scripts/setup-dev.sh`](src/kit/scripts/setup-dev.sh) | One-time setup after clone: `core.hooksPath`, `fetch.prune`, `pull.ff only`, `push.autoSetupRemote` |
| [`src/kit/.github/workflows/ci.yml`](src/kit/.github/workflows/ci.yml) | Jobs `test`, `secret-scan`, `pr-title`; read-only token, actions pinned to commit SHAs, PR title passed via `env` |
| [`src/kit/.github/rulesets/protect-main.json`](src/kit/.github/rulesets/protect-main.json) | Repository ruleset body for the REST API |
| [`src/kit/scripts/apply-ruleset.sh`](src/kit/scripts/apply-ruleset.sh) | Create or update the ruleset by name with `gh api` (idempotent) |
| [`src/kit/scripts/configure-repo.sh`](src/kit/scripts/configure-repo.sh) | Squash-only merges, squash commit = PR title + body, delete branch on merge |
| [`src/kit/.github/CODEOWNERS`](src/kit/.github/CODEOWNERS), [`pull_request_template.md`](src/kit/.github/pull_request_template.md) | Review routing and PR checklist (`@contoso/...` teams are placeholders) |
| [`src/kit/.gitattributes`](src/kit/.gitattributes), [`.gitignore`](src/kit/.gitignore) | LF for hooks/scripts, binaries marked binary, secrets and build output ignored |
| [`tests/`](tests/) | 54 pytest tests: unit tests plus **real `git commit` runs** in throwaway repos and the `gh` scripts against a fake `gh` |

## Run the tests

```bash
cd series/developer-tools/episodes/01-git-github-best-practices
python3 -m pip install pytest pyyaml          # if missing
python3 -m pytest -q                          # 54 passed in ~3.5 s
```

The end-to-end tests create temporary repos with an isolated `HOME` (your global Git config is not read), copy the
kit in, run `scripts/setup-dev.sh` and make real commits: good and bad messages, a commit on `main`, a staged token,
an oversized file, `--fixup`, `--no-verify`, and a hook saved with CRLF line endings.
The `gh` scripts run against a fake `gh` placed first on `PATH` that records every call, so the exact
methods, paths and fields are asserted without touching GitHub.

## Use it in a repository

```bash
cp -r src/kit/. ~/src/my-app/            # hooks, tools, .github, scripts, .gitattributes, .gitignore
cd ~/src/my-app
bash scripts/setup-dev.sh                # every developer, once per clone

# repo admin, once (needs: gh auth login, public repo on Free or Pro/Team/Enterprise for private repos)
scripts/configure-repo.sh  <owner>/<repo>
scripts/apply-ruleset.sh   <owner>/<repo>
```

Push a first PR before applying the ruleset, so the three check names (`test`, `secret-scan`, `pr-title`) exist.

## What we learned / gotchas

- **Hooks are advisory.** `git commit --no-verify` skips `pre-commit` and `commit-msg` (documented in githooks), and
  client-side hooks are not copied by `git clone`. That's why the same checks run again in CI and the ruleset makes
  those checks required. A test proves it: a `--no-verify` commit with a token succeeds locally and `scan-tree` fails.
- **Scan the index, not the working tree.** A developer can fix a secret in the editor and forget to `git add` again.
  `staged_checks` reads `git show :path`, so the commit is still blocked until the fix is staged (tested).
- **A hook saved with CRLF fails with `/usr/bin/env: 'python3\r': No such file or directory`.** We reproduced it.
  `.gitattributes` pins `.githooks/*`, `*.sh` and `*.py` to `eol=lf` so checkouts are right on every OS.
- **Squash merge uses the PR title as the commit message** for multi-commit PRs by default (single-commit PRs use the
  commit message). `configure-repo.sh` sets `squash_merge_commit_title=PR_TITLE`, and the `pr-title` job checks it.
- **Script injection:** the PR title is attacker-controlled. It goes into an `env:` variable, never `${{ }}` inside
  `run:`; a test fails the build if any `run:` contains `${{`.
- **Required check names are job names.** The ruleset's `context` values must match `name:` of the jobs; a test
  compares them so renaming a job can't silently block every PR.
- **YAML 1.1:** PyYAML loads the workflow's `on:` key as boolean `True`. The workflow is fine for GitHub; the test
  just reads both keys.
- **Fake secrets in tests are built at runtime** (`"ghp" + "_" + ...`) so the test files themselves pass the scan
  and GitHub push protection has nothing to flag in this repo.
- Not installed here: `actionlint`/`check-jsonschema` (no global tools on the shared build machine). The workflow is
  validated by the structural tests above; add `actionlint` to your own CI if you can.

## References
- [Adopt a Git branching strategy](https://learn.microsoft.com/azure/devops/repos/git/git-branching-guidance) (feature branches, PRs, high-quality `main`, naming conventions)
- [Development lifecycle: branch strategy](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/considerations/development-strategy-development-lifecycle) (branch policies, PR templates, delete merged branches)
- [Migrate to Git from centralized version control](https://learn.microsoft.com/devops/develop/git/centralized-to-git) (short-lived topic branches, feature flags)
- [githooks](https://git-scm.com/docs/githooks) (`core.hooksPath`, `--no-verify`) · [Pro Git: Git Hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks) (hooks are not copied on clone)
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
- GitHub docs: [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) ·
  [Rules REST API](https://docs.github.com/en/rest/repos/rules) ·
  [Update a repository](https://docs.github.com/en/rest/repos/repos#update-a-repository) ·
  [API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions) ·
  [About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) ·
  [Configuring commit squashing](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/configuring-commit-squashing-for-pull-requests) ·
  [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use) ·
  [About large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) ·
  [Token prefixes](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github) ·
  [About push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- Blog: [Git & GitHub Best Practices — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-28-git-github-best-practices-complete-guide-2025/)
