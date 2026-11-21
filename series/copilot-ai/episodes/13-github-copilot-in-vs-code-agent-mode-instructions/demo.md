# Demo shot list - Copilot & AI #13 GitHub Copilot in VS Code: Agent Mode, Instructions and Prompt Files

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | **None.** The Hyper-V lab (10.50.0.0/24) is not used |
| Tenant / Azure | Not used. No Azure resources, cost 0 for infrastructure |
| Accounts | The owner's GitHub account (the one that owns `github.com/devladlog/mg-lab`), signed in to VS Code. **Which Copilot plan it has must be confirmed on the recording day** (series plan). If it has no plan, VS Code enrols an eligible account in Copilot Free (VS Code docs), whose allowance may run out during the take: check the usage dashboard (Copilot icon in the Status Bar) before recording and say the plan name on screen or in the description. No GitHub PAT, nothing typed on camera |
| Licences / purchases | GitHub Copilot access only. Nothing is bought by this episode. Models used through Copilot consume AI credits of the plan. No price is quoted in the video; the docs page does not list one |
| Recording machine | Windows lab laptop, VS Code (stable, current) with the GitHub Copilot sign-in, Python 3.11+ on PATH (`python --version`), Git, PowerShell 7 terminal. Dark theme, font 18 pt, window 1600x900 |
| Network | Outbound HTTPS to GitHub Copilot; the folder is local, no remote repo needed (a local `git init` gives the diff) |

## What was verified where

| Step | Verified in the build container (Linux) | Needs the recording machine |
|---|---|---|
| Workspace baseline tests (4), acceptance tests fail before / pass with the reference patch, customcheck check / explain / convert | yes: `python -m pytest` in the episode folder, 32 passed | - |
| Everything in VS Code: harness picker, agent run, References, Customizations editor, Migrations tab | no | **record it** |
| What the real Copilot Agent does with the task | no (not run: it needs the Copilot sign-in) | **record it; keep the real result** |
| Whether the Local harness is still selectable | no | **check on the day** (docs: removed by February 2027) |

## Prerequisites
- `python -m pip install -r src/requirements.txt` in the episode folder (for customcheck; the sample workspace itself needs no packages).
- Copy `src/contoso-vendor-tools` to `C:\demo\contoso-vendor-tools` and run `git init; git add .; git commit -m baseline` inside it
  (so the agent's changes show in `git diff`). **Do not commit `acceptance/reference-solution.patch` to a public repo before
  recording** if the agent can see it: delete that one file from the demo copy (the tests in `acceptance/` stay).
- In the copy, `python -m pytest` -> `4 passed`; `python -m pytest acceptance -q` -> error / failure (expected, the feature does not exist yet).
- `python -m customcheck check C:\demo\contoso-vendor-tools` (from `src`) -> 0 errors, 0 warnings, 1 note.
- Open the folder in VS Code and **trust the workspace** (the agent runs commands).
- Decide the permission level before recording (Manual by default; the Chat view's permission picker). Do not use *Allow all*
  on camera: the docs say it skips ordinary confirmations including for destructive actions.

## Setup
1. VS Code: hover the Copilot icon in the Status Bar, **Use AI Features**, sign in with the owner's account (off camera).
2. Open Chat view, new chat, **Session Target**: confirm **Copilot** is offered. Note whether **Local** is also offered.
3. Run the task once off camera to know the length of the run and whether the plan allowance is enough. Then reset
   with `git checkout . ; git clean -fd` in the demo copy, so the recording starts from the baseline.

## Screens to capture (match the `screen` scenes in script.yaml)

| Scene id | File | What must be on screen |
|---|---|---|
| `harness-screen` | `screens/harness.jpg` | Chat view new chat, Session Target = **Copilot**; agent picker open: Ask, Agent, Plan and the custom agent **Renewal reviewer**. Second take: Command Palette **Chat: Open Customizations** > **Instructions**: `copilot-instructions.md`, `python-tests`, `cli` listed. Mask the GitHub account |
| `agent-screen` | `screens/agent-run.jpg` | Agent selected. Prompt exactly: *Show the notice deadline (renewal date minus notice_days) for each vendor in the renewals report, and flag vendors whose deadline has already passed.* Capture the run: files read, edits to `renewals.py` and `cli.py`, tests added, `python -m pytest` in the terminal, the final answer with the **References** section expanded (instruction files listed). Approve tool prompts on camera. Keep whatever happens |
| `verify-screen` | `screens/acceptance.jpg` | Terminal: `python -m pytest` and `python -m pytest acceptance -q`; then `git diff --stat`; `git diff -- tests` to read the new test names against `test_<behavior>_<condition>`; `Select-String -Path tests\*.py -Pattern "date.today"` to check the rule. **Record the real verdict.** If the agent broke a rule or failed the acceptance test, keep the take and rewrite the narration of `agent-screen` / `verify-screen` before publishing (the script assumes a pass) |
| `prompt-gotcha` | `screens/prompt-local.jpg` | Type `/` in a **Copilot** chat: list what appears (the skill `renewal-report` should be there; record whether `renewal-report-prompt` is). If Local is still offered: new chat with Session Target **Local**, `/` shows the prompt file. Then **Chat: Open Customizations** > **Migrations** with the **Convert Prompt to Skills** section. If the Local harness is gone: record the Copilot chat and the Migrations tab only and change the narration "and the Local harness is removed by February twenty twenty seven" to the past tense |

Optional extra take (not in the script): `python -m customcheck explain` and `convert-prompt` in the terminal, to match the `convert` code scene
(the scene shows the real output of the commands in the README).

## Masking notes
- GitHub account name and avatar (Status Bar, Copilot dashboard), any email in the account menu.
- Folder path if it contains the Windows user name: record from `C:\demo\...`.
- No tenant is shown in this episode.

## Tear-down
- Close the chat sessions (Manage Sessions: archive them).
- Delete `C:\demo\contoso-vendor-tools`.
- Nothing is created in GitHub or Azure. If the owner's Copilot plan was changed for the recording, restore it.
