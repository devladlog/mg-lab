# DEVLADLOG Dev Tools #7 — Code review best practices: automate the boring half, review the rest properly

A real pull request to the orders API from [episode 5](../05-ci-cd-pipeline-setup/) ("cancel an order", two commits), a review of it, and the small
**review kit** that does the mechanical half of the job: the size a human has to read, whether the description gives the reviewer a map, who has to review
which files, whether the review comments say how serious they are, and how long pull requests wait. Episode 1 already covers rulesets, required approvals and
code owners as enforcement; this episode is about what happens *inside* the review.

```
author:    pull_request_template.md (4 sections for the reviewer) ──► pr-description ✓
machines:  git diff base...head ──► pr-size (lines a person reads, per area, size/S..XL)
           CODEOWNERS            ──► review-routing (who, per file)             (workflow: pr-review-kit.yml, 3 jobs)
humans:    labelled comments (Conventional Comments) + a GitHub suggestion  ──► review_kit comments (lint + blocking list)
proof:     the reviewer's reproduction fails on commit 1, passes on commit 2 (src/review-demo)
queue:     gh api pulls + reviews ──► review_kit metrics (hours to first review, to merge)
```

| Path | What it is |
|---|---|
| [`src/orders-app/tools/review_kit/size.py`](src/orders-app/tools/review_kit/size.py) | `git diff --numstat -z -M base...head` → lines per area, lock files/generated/snapshots ignored, label S/M/L/XL (team defaults 100/300/600), split hint |
| [`src/orders-app/tools/review_kit/description.py`](src/orders-app/tools/review_kit/description.py) | The four required sections exist and hold at least 20 characters of the author's words (template comments, bare checkboxes and `TBD`/`N/A` don't count) |
| [`src/orders-app/tools/review_kit/owners.py`](src/orders-app/tools/review_kit/owners.py) | CODEOWNERS the way GitHub reads it: last match wins, gitignore-style patterns, unsupported syntax and bad owners reported, files nobody owns listed |
| [`src/orders-app/tools/review_kit/comments.py`](src/orders-app/tools/review_kit/comments.py) | Conventional Comments parser and lint (house rule: issue/question/todo/chore must say blocking or non-blocking), blocking list |
| [`src/orders-app/tools/review_kit/metrics.py`](src/orders-app/tools/review_kit/metrics.py) | Time to first review (not the author, not pending drafts), time to merge, changes requested, reviewers; `fetch` uses `gh api` |
| [`src/orders-app/tools/review_kit/cli.py`](src/orders-app/tools/review_kit/cli.py) | `size`, `description`, `owners`, `comments`, `metrics`; Markdown to stdout and `$GITHUB_STEP_SUMMARY`; `label=size/M` to `$GITHUB_OUTPUT` |
| [`src/orders-app/.github/workflows/pr-review-kit.yml`](src/orders-app/.github/workflows/pr-review-kit.yml) | Jobs `pr-size`, `pr-description`, `review-routing`; triggers include `edited`; read-only token; checkout pinned to a commit; PR text only through `env` |
| [`src/orders-app/.github/pull_request_template.md`](src/orders-app/.github/pull_request_template.md), [`CODEOWNERS`](src/orders-app/.github/CODEOWNERS) | The reviewer-oriented template (extends episode 1's) and a routing file (`@contoso/...` placeholders) |
| [`src/orders-app/`](src/orders-app/) (rest) | Episode 5's API and xUnit tests as the baseline `main` (no Docker/Azure files: not needed here) |
| [`src/review-demo/0001-…patch`, `0002-…patch`](src/review-demo/) | The pull request as two `git format-patch` commits by "Alex Demo": the change as submitted, and the follow-up after review |
| [`src/review-demo/CancelRepro.cs`](src/review-demo/CancelRepro.cs) | The reviewer's two reproductions, written against commit 1 |
| [`src/review-demo/review-comments.json`](src/review-demo/review-comments.json), [`review-payload.py`](src/review-demo/review-payload.py) | The review as GitHub's REST API returns it (7 comments, 2 replies, one multi-line suggestion), and a script that turns it into the body of *Create a review* |
| [`src/review-demo/pr-body.good.md`](src/review-demo/pr-body.good.md), `pr-body.bad.md` | A description that passes and one that fails every section |
| [`tests/`](tests/) | 69 pytest tests (below) |

## Run the tests

```bash
cd series/developer-tools/episodes/07-code-review-best-practices
python3 -m pytest -q tests                                     # 69 passed (~90 s: real git repos, 4 dotnet builds, one dotnet run)
(cd src/orders-app && dotnet test)                              # baseline main: Passed! 21 passed, 4 skipped (SQL Server tests, no SQL Server here)
rm -rf src/orders-app/src/*/bin src/orders-app/src/*/obj src/orders-app/tests/*/bin src/orders-app/tests/*/obj
```

| Test file | What it proves |
|---|---|
| `test_size.py` (9) | On **real git history** in throwaway repos: numstat counts, a rename is one change with 0 lines, binary files listed with no lines, three-dot diff ignores what happened on `main` after the branch was cut, lock files/generated/snapshots/`node_modules` not counted, areas ranked and a split hint for XL, boundaries of the labels, CLI exit code and `GITHUB_OUTPUT`/`GITHUB_STEP_SUMMARY`, bad revision = exit 2 |
| `test_description.py` (10) | The demo PR body passes; placeholders, `TBD`, `N/A`, bare checkboxes and template comments don't count; missing section; case-insensitive headings and CRLF; a heading inside a code fence isn't a section; the template has exactly the sections the check requires; empty body fails every section |
| `test_owners.py` (16) | The shipped CODEOWNERS parses without warnings; last match wins on 7 paths; gitignore-style anchoring (`/x/`, `x/`, `*.md`, `**/x/`, `*` doesn't cross a slash); case sensitivity; a pattern with no owner removes the owner; owners split over two lines → only the last applies; `!`, `[ ]`, `\#` and bad owners are warnings and the line is skipped; routing on a real branch; `--require-owner` |
| `test_comments.py` (13) | Label/decoration parsing; the demo review is clean with 7 comments, 2 replies and 3 blocking; house rules; the suggestion block is a GitHub suggestion; CLI exit codes; the review payload has the shape of *Create a review* (multi-line comment, no `commit_id`, event `COMMENT`) |
| `test_metrics.py` (7) | First review ignores the author and `PENDING` drafts; no first review → `None`; closed-unmerged; median; **`fetch` run against a fake `gh`** on PATH (list → each PR → its reviews) and the CLI end to end; a failing `gh` is exit 2 |
| `test_workflow.py` (9) | Schema; job names = ids; `edited` is a trigger; read-only token; checkout pinned to the recorded commit and every input exists; PR text only via `env`; scripts named exist; **the three jobs' `run:` lines executed with the env GitHub provides on a real branch**, and the description job fails on an empty body |
| `test_demo_pr.py` (5) | **`git am` of both patches onto the baseline**; commit 1 is `size/S`, 31 lines (22 test, 9 source); CODEOWNERS routes it to the orders team (+ qa for tests); every comment's line really holds the code it talks about; **dotnet test**: commit 1 green (22 passed), plus the reviewer's repro → 2 failed (500 instead of 404, 200 instead of 409), **GitHub's suggestion applied exactly as written** → only the 409 repro still fails, commit 2 green (24 passed); an old-schema SQLite file makes the new code answer 500 (`no such column: o.Status`) |

**Not run here:** the workflow on GitHub-hosted runners, the GitHub UI, and any call to the real GitHub API (`metrics` and `review_kit comments` read from a fake `gh` and from
JSON shaped like the documented responses; the real calls are made in the recording, see [demo.md](demo.md)). Whether the *Create a review* API accepts our multi-line
suggestion comment is not verified (GitHub's docs list `start_line` and `start_side` without describing them); demo.md has a fallback.

## What we learned / gotchas

- **Green CI, still a 500.** The author's commit has a test and it passes (22 passed). `order!.Status = ...` tells the compiler the order isn't null; for an unknown id it
  throws and the caller gets 500 (`Expected: NotFound  Actual: InternalServerError`); cancelling twice answers 200 (`Expected: Conflict  Actual: OK`). The review's value is
  the comment *with a reproduction attached*: `src/review-demo/CancelRepro.cs`.
- **A suggestion replaces exactly the lines it is anchored to.** My first suggestion was anchored on lines 54–55 (declaration and use) and contained only the guard
  clause: applied as GitHub would, the assignment was gone and the author's own test failed (`Expected: "cancelled"  Actual: "open"`). The test applies the suggestion text to the
  file before the follow-up is accepted. Build and test a suggestion before posting it. (GitHub's doc: suggestions are a ```` ```suggestion ```` block in the comment; the author
  commits them.)
- **`pull_request` doesn't fire on `edited` by default.** GitHub's docs: by default only `opened`, `synchronize` and `reopened`. A description check that doesn't list
  `edited` would stay green after someone empties the description. The workflow lists it, and a test pins it.
- **Measure what a pull request adds with three dots.** `git diff main...feature` is the change since the branch left `main` (what the PR shows); two dots would include
  everything that landed on `main` since (a test adds 500 lines to `main` and the PR still measures 7). `git diff --numstat -z -M` writes a rename as an empty path followed by
  two records, and binary files as `-` `-`: both handled and tested on real repos.
- **Size limits are ours.** 100/300/600 changed lines is a team default in one constant, not a published standard, and no source is claimed for it. Lock files, generated
  code and snapshots are excluded because nobody reviews them line by line (and `packages.lock.json` from episode 5 is the biggest diff in most dependency bumps).
- **CODEOWNERS, as GitHub documents it:** the last matching pattern wins; two lines for the same pattern don't add up, only the last applies; `!`, `[ ]` and an escaped leading
  `#` aren't supported and the line is skipped; owners need write access (teams must be visible); a path with no owner can be approved by any writer; drafts don't request owners; any
  one of several owners satisfies "Require review from Code Owners". The `@contoso/...` teams in the file are placeholders: on a real repo they would request nobody, so
  demo.md replaces them with the account.
- **Authors can't approve their own pull request** (GitHub docs), and the lab has one GitHub identity. The demo is a comment review, says so, and shows no approval. The
  ruleset from episode 1 is what requires a second person in a team; it isn't applied to the throwaway repo.
- **Say the risk in the description, and check it.** The good description's *Risk and rollback* says the demo app creates its schema with `EnsureCreated`, so an existing
  database wouldn't get the new column. Microsoft Learn: *"If any tables exist ..., the schema won't be initialized."* A test creates an old-schema SQLite file, starts the
  new code and gets 500 with `no such column: o.Status`. The deployed container's data resets on every deploy (episode 5), which is why this PR is still safe to ship; a database
  that survives deploys would need migrations first. Learn also says `EnsureCreated` and migrations don't mix.
- **Metrics from the REST API:** the *list pull requests* example has no `additions`/`deletions`, so `fetch` calls *get a pull request* for each one; reviews in `PENDING` have no
  `submitted_at` (docs) and are ignored; the author's own review isn't a first review. The numbers find a queue; they don't rank people, and the kit prints no per-person ranking on purpose.
- **Conventional Comments** (conventionalcomments.org): labels praise, nitpick, suggestion, issue, todo, question, thought, chore, note (plus typo, polish, quibble); decorations
  (blocking), (non-blocking), (if-minor); the spec calls decorations optional and warns against piling them up. The rule "issue, question, todo and chore must say blocking or
  non-blocking" is *ours*, because without it the author has to guess. Azure Repos has the same ideas natively: votes (Approve, Approve with suggestions, Wait for author, Reject),
  comment statuses (Active, Pending, Resolved, Won't fix, Closed), and suggested changes with *Apply changes*.

## References
- Blog: [Code Review Best Practices — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-24-code-review-best-practices-complete-guide-2025/)
- Microsoft Learn: [Review pull requests (Azure Repos)](https://learn.microsoft.com/azure/devops/repos/git/review-pull-requests?view=azure-devops) (votes, comment statuses, suggested changes, review practice) ·
  [EnsureCreated and EnsureDeleted (EF Core)](https://learn.microsoft.com/ef/core/managing-schemas/ensure-created) (schema isn't initialized when tables exist; not for use with migrations)
- GitHub docs: [About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) (syntax, precedence, write access, drafts) ·
  [Reviewing proposed changes in a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/reviewing-proposed-changes-in-a-pull-request) (review types, authors can't approve, suggested changes) ·
  [Events that trigger workflows: pull_request](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) (default activity types, `edited`, `GITHUB_SHA`) ·
  REST: [pull request review comments](https://docs.github.com/en/rest/pulls/comments), [reviews](https://docs.github.com/en/rest/pulls/reviews) (create a review, `PENDING`, `submitted_at`), [pull requests](https://docs.github.com/en/rest/pulls/pulls)
- Spec: [Conventional Comments](https://conventionalcomments.org/)
- Actions used: `actions/checkout` v7.0.1 at the commit recorded in `tests/fixtures/actions/pins.json`
