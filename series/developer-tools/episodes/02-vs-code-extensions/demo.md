# Demo shot list — DEVLADLOG Dev Tools #2, VS Code extensions

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant / Azure | none (no Microsoft tenant, no cloud resource) |
| Software | VS Code 1.100+ with a clean profile "DevTools Demo" (created and deleted in the episode), Git, Node 22, Python 3.10+ |
| Identity in commits | `Alex Demo` / `alex.demo@contoso.com` in the sample repo (fictional, matches the lab persona) |
| Licences / cost | none |
| Recording machine | The Windows lab laptop: VS Code (Extension Development Host for the extension), Git Bash for the setup commands, sample repo under a neutral path such as `C:\MGLab\demo\orders-app` (`~/demo/...` below) |

Everything except the three `screen` scenes is already real (code excerpts, `npm test` 15 passed, `pytest` 13 passed,
`vsce package` output and the `@types/vscode` error, all captured on the build machine). No Microsoft tenant or cloud
resource is involved. The live part needs **VS Code on a desktop** (Windows, macOS or Linux). Status: **needs desktop**
for `recommendedview`, `validate` and `commitbox`.

## Prerequisites
- VS Code 1.100 or later, Git, Node 22, Python 3.10+. Cost: none.
- A **clean profile** for the first screen, so no extension is installed yet:
  `code --profile "DevTools Demo" src/team-setup` (the docs say a missing profile is created empty).
  Delete it afterwards (Profiles editor).
- The episode 1 kit for the last screen (the hooks), from `../01-git-github-best-practices/src/kit`.
- Display 1920×1080, VS Code zoom so text is readable at 1080p (`window.zoomLevel` 1), Dark Modern theme.

## Setup
```bash
cd series/developer-tools/episodes/02-vs-code-extensions/src/mg-commit
npm ci --no-audit --no-fund && npm run compile

# a sample repo with the episode 1 hooks and a staged change
mkdir -p ~/demo/orders-app && cd ~/demo/orders-app
cp -r <mg-lab>/series/developer-tools/episodes/01-git-github-best-practices/src/kit/. .
cp -r <mg-lab>/series/developer-tools/episodes/02-vs-code-extensions/src/team-setup/.vscode .
git init -b main && bash scripts/setup-dev.sh
git config user.name "Alex Demo" && git config user.email alex.demo@contoso.com
git add . && git commit -m "chore: add repo guardrails"
git switch -c feature/orders-paging
mkdir -p src && echo 'PAGE_SIZE = 50' > src/orders.py && git add src/orders.py
```

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `recommendedview` | `screens/recommended.jpg` | `code --profile "DevTools Demo" src/team-setup` (first open of that folder in that profile). The notification "Do you want to install the recommended extensions…" (bottom right) and the Extensions view with `@recommended` showing **Workspace Recommendations** with the seven ids from `extensions.json`. Don't click Install on camera if it would take long; one capture with both visible is enough. |
| `validate` | `screens/validate.jpg` | Open `src/mg-commit` in VS Code, F5 (**Run Extension**). In the Extension Development Host open `~/demo/orders-app`. Source Control view → pencil icon (or Command Palette → **MG: Compose Conventional Commit**). Pick `feat`, scope `orders`, `No`. In the subject box type `Added paging.` → capture the message "Start with a lower-case verb: add, fix, remove...". Optional second capture: a long subject showing "Header is 7x/72 characters: shorten the subject". |
| `commitbox` | `screens/commitbox.jpg` | Before running the command, type a body in the commit box: line 1 `wip`, line 3 `Uses cursor paging.`. Run the command with subject `add paging`. Capture the commit box with `feat(orders): add paging` / blank / `Uses cursor paging.` Then commit (Ctrl+Enter) and show the integrated terminal with `git log --oneline -1`. |

Extra check during recording (not a scene, but confirm it): in a multi-root workspace with two repos, the pencil
button in each repository's Source Control title bar fills **that** repo's commit box. If it falls back to the picker
instead, note it in the README gotchas (the code handles both).

Optional b-roll for the `audit` scene: in the demo profile after installing four of the seven recommendations,
`python3 tools/ext_audit.py` in the integrated terminal (real versions will differ from the script excerpt; the
narration doesn't read them out).

## Masking
- Nothing secret is on screen. Hide the OS username in the terminal prompt (`PS1='$ '`) and in the VS Code title
  bar/breadcrumbs if the home path shows it (open folders from a neutral path like `~/demo`).
- Signed-in account (Accounts icon, Settings Sync): sign out in the demo profile or crop the activity bar bottom.

## Tear-down
1. Profiles editor → delete **DevTools Demo**.
2. `code --uninstall-extension contoso.mg-commit` if the `.vsix` was installed.
3. `rm -rf ~/demo/orders-app`, and in `src/mg-commit`: `rm -rf node_modules out *.vsix`.
