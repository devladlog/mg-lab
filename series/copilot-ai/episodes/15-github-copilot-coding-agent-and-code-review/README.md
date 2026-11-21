# DEVLADLOG Copilot & AI #15 - GitHub Copilot Coding Agent and Code Review

Contoso Bikes has a small pricing library and a pricing bug nobody has time for. This episode hands the issue to the
**GitHub Copilot cloud agent** (GitHub's current name; it was the *Copilot coding agent*), lets **Copilot code review**
read a flawed pull request, and shows the guardrails that keep a human in charge. Everything GitHub does is recorded for
real on a throwaway repository; what we built is the **preflight kit** around it, with tests:

- is the issue written so an agent can finish it (and is there hidden text it will never see);
- is `copilot-setup-steps.yml` valid by the documented rules;
- are the instruction files lint-clean (frontmatter, `applyTo` matches files, nothing code review does not support);
- the exact REST calls that assign an issue to Copilot and request a Copilot review (dry run by default);
- a read-only gate: is the agent's pull request ready for a human to merge?

Series plan: [`../../README.md`](../../README.md) ("Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Category episodes this builds on: [Git & GitHub best practices](../../../developer-tools/episodes/01-git-github-best-practices/)
(rulesets, required approvals), [CI/CD pipeline setup](../../../developer-tools/episodes/05-ci-cd-pipeline-setup/) and
[Code review best practices](../../../developer-tools/episodes/07-code-review-best-practices/) (human review, labelled
comments). Next: episode 16, *GitHub Copilot for .NET Modernization* (its Learn page also shows the upgrade agent running as a
cloud-agent custom agent). Episodes 13 and 14 of this series (VS Code agent mode, MCP servers) are not built yet.

| Path | What it is |
|---|---|
| [`src/agent_ready/setup_steps.py`](src/agent_ready/setup_steps.py) | Validates `copilot-setup-steps.yml`: job name, honoured keys, `timeout-minutes` <= 59, `contents: read` for checkout, runner support, triggers |
| [`src/agent_ready/issue_lint.py`](src/agent_ready/issue_lint.py) | "Ready to assign" checklist: problem with an example, checklist criteria with values and tests, file paths, vague words, HTML-comment text |
| [`src/agent_ready/instructions.py`](src/agent_ready/instructions.py) | Finds and lints `.github/copilot-instructions.md`, `.github/instructions/**/*.instructions.md`, `AGENTS.md` |
| [`src/agent_ready/assign.py`](src/agent_ready/assign.py) | Builds the documented REST requests (`copilot-swe-agent[bot]` + `agent_assignment`; `copilot-pull-request-reviewer[bot]`); sends them through `gh api` only with `--execute` |
| [`src/agent_ready/review_gate.py`](src/agent_ready/review_gate.py) | Read-only merge-readiness check from the pull request, its reviews and the workflow runs of the head commit |
| [`src/agent_ready/cli.py`](src/agent_ready/cli.py) | `setup-steps`, `issue`, `instructions`, `assign`, `review`, `gate` |
| [`src/demo-repo/`](src/demo-repo/) | The throwaway repository: .NET 8 pricing library + xunit tests, `copilot-instructions.md`, two path instruction files, `copilot-setup-steps.yml`, `ci.yml`, two issues (one ready, one deliberately vague) |
| [`src/demo-repo/review-demo/0001-add-bulk-discount.patch`](src/demo-repo/review-demo/0001-add-bulk-discount.patch) | A pull request with four planted problems (`double` for money, `Math.Round` without the midpoint rule, no validation, swallowed exception). It builds and its test passes, so only a reviewer finds them |
| [`tests/`](tests) | 59 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes) and recording shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/15-github-copilot-coding-agent-and-code-review
python3 -m pip install -r src/requirements.txt          # PyYAML, pytest
python3 -m pytest -q                                     # 59 passed
cd src
python3 -m agent_ready setup-steps demo-repo/.github/workflows/copilot-setup-steps.yml   # OK
python3 -m agent_ready issue demo-repo/issues/01-ready-loyalty-rounding.md                 # ready to assign
python3 -m agent_ready issue demo-repo/issues/02-vague-make-pricing-better.md              # 2 errors, 3 warnings, exit 1
python3 -m agent_ready instructions demo-repo                                              # OK
python3 -m agent_ready assign OWNER/REPO 1 --instructions "Run dotnet test before finishing"   # dry run: prints the request
cd demo-repo && dotnet test Contoso.Bikes.sln                                              # 8 passed (9 with the review patch)
```

Against the real service (needs the owner's GitHub account and a paid Copilot plan; see `demo.md`):

```bash
python3 -m agent_ready assign OWNER/contoso-bikes-pricing 1 --execute          # or assign in the issue sidebar
python3 -m agent_ready review OWNER/contoso-bikes-pricing 2 --execute          # or Reviewers > Copilot
python3 -m agent_ready gate --repo OWNER/contoso-bikes-pricing --pull 3 --requested-by OWNER
```

Verified here: pytest 59 passed (Python 3.13); `dotnet test` on the demo repo 8 passed, and on a copy with the review
patch applied (`git apply --check` clean) 9 passed (.NET 8 SDK, xunit 2.9.2).
Needs the real GitHub account: assigning, the agent session, the Copilot review, `assign --execute`, `review --execute`
and `gate --repo`. The REST and `gh` calls are tested only against a fake runner.

## What we learned / gotchas

- **The name changed.** GitHub's docs now say *Copilot cloud agent*; older pages and Microsoft Learn's training module
  still say *coding agent*. The REST assignee is still `copilot-swe-agent[bot]`.
- **The issue is the prompt.** Per GitHub, the agent gets the issue title, description and comments plus the repository
  instructions, and it does **not** react to comments added after assignment (comment on the pull request instead).
- **Hidden text is filtered.** Text in an HTML comment of an issue or pull request comment is not passed to the agent
  (GitHub "Risks and mitigations"), so `02-vague-make-pricing-better.md` carries an instruction the agent will never read.
- **Setup steps are strict.** Job must be named `copilot-setup-steps`; only `steps`, `permissions`, `runs-on`, `services`,
  `snapshot`, `timeout-minutes` (max 59) are honoured; the file must be on the default branch; `fetch-depth` is overridden.
  Only Ubuntu x64 and Windows 64-bit runners are supported, and the integrated firewall is not compatible with Windows.
- **Nothing runs until a person approves.** The agent's changes do not trigger workflows until someone with write access
  clicks *Approve and run workflows*; auto-run is an optional setting. The gate reports "no workflow runs" or runs with
  conclusion `action_required` as waiting. The `action_required` mapping is our reading of the API, not documented text:
  confirm it on the first real run and fix `review_gate.py` if the runs look different.
- **The requester cannot approve.** And the agent cannot mark ready, approve or merge. With a personal repository you need
  a second account with write access to record the "approved" half of the gate.
- **Copilot's review is advisory.** It is a "Comment" review and does not count toward required approvals. Approvals by
  Copilot are a public preview and off by default. It does not see replies to its comments and a re-review can repeat
  comments you resolved. Effort can be *Lite* or *Balanced*.
- **Review instructions limits changed.** The old 4,000 character limit for code review instructions was removed (GitHub
  changelog, 12 June 2026); the docs now advise about 1,000 lines per file. Not supported: formatting or UX of the review
  comment, changing the overview comment, blocking merges, changelog entries, external links, vague requests ("be more
  accurate"). `instructions.py` flags these.
- **Billing is moving.** The plans page (read 21 Nov 2026) lists Copilot Pro $10, Pro+ $39, Max $100, Business $19 and
  Enterprise $39 per month and talks about *AI credits*; the cloud agent page says the agent uses Actions minutes and AI
  credits and code review uses Actions minutes on private repositories. "Request-based billing (legacy)" pages still
  exist. Re-read the pages on the recording day.
- **API in preview.** The issue-assignment REST/GraphQL API is documented as public preview and works only with
  user-to-server tokens (a personal access token, an OAuth app token such as the one `gh auth login` creates, or a GitHub
  App user-to-server token), not installation tokens.

## References

- Overview of Copilot cloud agent: <https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent>
- Use cloud agent on GitHub (assign an issue): <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-on-github>
- Use cloud agent via the API: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/use-cloud-agent-via-the-api>
- Customize the agent environment (`copilot-setup-steps.yml`): <https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/customize-the-agent-environment>
- Risks and mitigations: <https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations>
- Use Copilot code review: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review>
- Customize code review: <https://docs.github.com/en/copilot/tutorials/customize-code-review>
- Copilot plans: <https://docs.github.com/en/copilot/get-started/plans>
- Changelog, code review instructions limit removed (12 Jun 2026): <https://github.blog/changelog/2026-06-12-copilot-code-review-new-configurations-and-controls/>
- Microsoft Learn training module "Copilot cloud agent": <https://learn.microsoft.com/training/modules/github-copilot-code-agent/>
- No blog Complete Guide: this series is built from official documentation only.
