# DEVLADLOG Copilot & AI #13 - GitHub Copilot in VS Code: Agent Mode, Instructions and Prompt Files

Contoso's Vendor Management Office has a small Python tool (the renewal report for the four fictional vendors of
episodes 2 and 3) and a Copilot that keeps missing the team's rules. This episode writes those rules as Copilot
customization files, lets the Copilot **Agent** do a real task in VS Code, checks the result with an acceptance test the
agent never saw, and finds out the thing the title does not say: **prompt files only run in the deprecated Local
harness** (removal announced for February 2027), so new reusable workflows belong in **skills**.

What was built (all of it runs here):

- **`src/contoso-vendor-tools/`**, the workspace the demo opens in VS Code: a tiny Python package (`vendor_tools`, standard
  library only), its tests, and the customization files:
  `.github/copilot-instructions.md`, two targeted `*.instructions.md` files with `applyTo`, a skill
  (`.github/skills/renewal-report/SKILL.md`), a Local-harness prompt file (kept on purpose, it is the gotcha) and a
  read-only custom agent (`.github/agents/renewal-reviewer.agent.md`).
- **`acceptance/`** inside that workspace: three tests for the live task ("show the notice deadline and flag the
  passed ones") that **fail on the untouched repo**, plus `reference-solution.patch`, which proves the task is
  achievable and that the tests pass for a correct solution. The recorder runs them after the agent finishes, so the
  screen shows a real verdict on the real agent output.
- **`src/customcheck/`**, a lint/explain/convert tool for these files, written from the VS Code documentation.

Series plan: [`../../README.md`](../../README.md) (read "Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 12, *Copilot for Windows Server Admins*. Next: episode 14, [GitHub Copilot with MCP Servers](../14-github-copilot-with-mcp-servers-learn-azure-github/).
Same vendors as [episode 2](../02-microsoft-365-copilot-chat-in-a-real-tenant/) and [episode 3](../03-copilot-studio-your-first-agent-with-sharepoint-kn/).
Category episodes this builds on: [VS Code extensions](../../../developer-tools/episodes/02-vs-code-extensions/),
[Code review best practices](../../../developer-tools/episodes/07-code-review-best-practices/) and
[Git and GitHub best practices](../../../developer-tools/episodes/01-git-github-best-practices/).
There is no devladlog.com Complete Guide for this series: every fact comes from the official documentation below.

| Path | What it is |
|---|---|
| [`src/contoso-vendor-tools/src/vendor_tools/`](src/contoso-vendor-tools/src/vendor_tools) | `renewals.py` (logic), `cli.py` (printing). Dates ISO, money in whole euros |
| [`src/contoso-vendor-tools/tests/`](src/contoso-vendor-tools/tests) | 4 baseline tests |
| [`src/contoso-vendor-tools/.github/`](src/contoso-vendor-tools/.github) | The customization files shown in the episode |
| [`src/contoso-vendor-tools/acceptance/`](src/contoso-vendor-tools/acceptance) | 3 acceptance tests for the live task, and the reference solution as a patch |
| [`src/customcheck/`](src/customcheck) | `check`, `explain`, `convert-prompt` (`python -m customcheck`) |
| [`tests/`](tests) | 32 pytest tests: the `applyTo` table from the docs, every lint rule, the converter, the sample workspace |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (14 scenes, about 800 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/13-github-copilot-in-vs-code-agent-mode-instructions
python3 -m pip install -r src/requirements.txt      # PyYAML, pytest
python3 -m pytest -q                                 # 32 passed (needs `patch` for one test)
cd src
python3 -m customcheck check contoso-vendor-tools    # 0 errors, 0 warnings, 1 note (the prompt file is Local only)
python3 -m customcheck explain contoso-vendor-tools tests/test_renewals.py
python3 -m customcheck convert-prompt contoso-vendor-tools/.github/prompts/renewal-report.prompt.md --skills-dir /tmp/skills
cd contoso-vendor-tools
python3 -m pytest -q                                 # 4 passed (the workspace's own tests)
python3 -m pytest acceptance -q                      # FAILS before the task: that is the point
```

Verified here: `python -m pytest` in the episode folder, **32 passed** (Python 3.13, pytest 9, PyYAML 6). The sample
workspace: 4 passed; acceptance tests: collection error (`notice_deadline` does not exist) on the untouched repo, and
`3 passed` plus the 4 baseline tests passing after `reference-solution.patch` is applied (that check is part of the 32).

**Needs the lab / the owner's GitHub account** (see `demo.md`): everything inside VS Code: signing in to GitHub Copilot,
the Chat view, the Agent run, the Customizations editor, the Migrations tab. **Not verified here:** how the real agent
behaves on the task (that is what the recording shows, kept as it is), and whether the Local harness is still
selectable on the recording day.

## What we learned / gotchas

All from the VS Code documentation pages dated 18 Nov 2026 (read 21 Nov 2026) unless marked.

- **New vocabulary.** VS Code now describes an agent **harness** (Copilot, Claude, Codex, Local) that runs the agent, and
  built-in agents in the Copilot harness: **Ask** (read-only), **Agent** (implements and validates) and **Plan**. The
  Learn pages for the Azure MCP server and the Learn MCP server still say "agent mode"; both names are in the wild.
  Choosing a Claude model inside a Copilot session does not switch to the Claude harness.
- **The Local harness is deprecated and removed by February 2027.** The editor docs say to move to the Copilot harness
  before then.
- **Instruction locations are per harness.** Copilot: `.github/copilot-instructions.md` or `AGENTS.md`, plus
  `.github/instructions/**/*.instructions.md` (or nested `AGENTS.md`). Claude: `CLAUDE.md`, `.claude/rules`. Codex:
  `AGENTS.md`. There is **no precedence rule** across harnesses or sources: keep sources consistent instead of relying on order.
- **`applyTo`**: one string, several globs separated by commas, **relative to the workspace root, not to the
  instructions folder**; `*.py` does not match `src/app.py`, `src/**/*.py` matches `src/app.py` (`customcheck` tests this
  table). `description` is only used for on-demand loading in Local sessions; "do not use a description as a substitute
  for a pattern".
- **Instructions are guidance, not enforcement.** The docs: they "don't guarantee compliance or replace tests, code
  review, or security controls", and they do not apply to inline suggestions. The References section of a response
  shows inclusion, not compliance. Hence the acceptance test.
- **Prompt files** (`.prompt.md`, `.github/prompts`, fields `description`, `name`, `argument-hint`, `agent`, `model`,
  `tools`; variables `${input:name:placeholder}`, `${selection}`; tool references `#tool:<name>`) **run only in Local
  harness sessions**. The Copilot harness does not load them. Recurring prompts should be converted to skills; for new
  workflows, create a skill.
- **Conversion to a skill** (documented behaviour, mirrored by `customcheck convert-prompt`): explicit invocation is
  kept by adding `disable-model-invocation: true`; the prompt's `agent`, `model` and `tools` are not preserved, and
  "a skill's instructions do not replace a tool allow-list". Removing the restriction lets the agent pick the skill
  automatically, so review the description first.
- **Skills** (`.github/skills/<name>/SKILL.md`; user-level `~/.copilot/skills/`): `name` is required, lowercase letters,
  numbers and hyphens, max 64 characters, must match the folder; `description` is required, max 1,024 characters.
  Invalid names "cause the skill to silently fail to load", and so do namespace prefixes such as `myorg:skill`.
- **Custom agents**: `.github/agents/*.agent.md` (`.chatmode.md` is the old name: rename). The Copilot schema requires
  `description`; `handoffs`, `agents`, `argument-hint` and `advancedOptions` are Local-only, `skills` and `mcp-servers`
  Copilot-only. In Copilot, `tools` accepts the aliases `execute`, `read`, `edit`, `search`, `agent`, `web`, `todo`, `*`.
- **Access and cost.** Without a Copilot plan, signing in enrols an eligible account in **Copilot Free**; models used
  through Copilot consume AI credits from the plan's allowance. The docs do not give a price on that page: confirm the
  owner's plan and allowance on the recording day (series plan: "confirm which plan at recording").
- **Our linter is not Microsoft's.** `customcheck` encodes the documented rules; `applyTo` matching is an offline
  approximation of the documented table, and `excludeAgent` is accepted because the docs name it as a GitHub-side field.

## References

VS Code documentation (pages dated 18 Nov 2026)
- [Choose an agent harness](https://code.visualstudio.com/docs/agents/run/agent-harnesses)
- [Use custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
- [Custom instructions reference](https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference)
- [Use prompt files](https://code.visualstudio.com/docs/agent-customization/prompt-files)
- [Use Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Move from the Local to the Copilot harness](https://code.visualstudio.com/docs/agents/run/move-to-copilot)
- [Migrate customizations](https://code.visualstudio.com/docs/agent-customization/migrate-customizations)
- [Custom agent file reference](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference)
- [Set up GitHub Copilot in VS Code](https://code.visualstudio.com/docs/setup/copilot)

Microsoft Learn (naming cross-check)
- [Get started with the Azure MCP Server using Visual Studio Code](https://learn.microsoft.com/azure/developer/azure-mcp-server/get-started/tools/visual-studio-code) (still says "agent mode")
- [Microsoft Learn MCP Server: get started](https://learn.microsoft.com/training/support/mcp-get-started)
