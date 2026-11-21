# DEVLADLOG Dev Tools #2 — VS Code extensions for a whole team

Two things you can drop into a repository:

1. **Team setup** (`src/team-setup/`): workspace recommendations, workspace settings with one formatter per
   language, an `.editorconfig`, and **`ext_audit.py`**, a script that compares the extensions installed on a machine
   with the recommendations and installs what's missing.
2. **MG Commit Helper** (`src/mg-commit/`): a small VS Code extension that composes a Conventional Commit message in
   the Source Control box (type → scope → breaking? → subject, validated as you type). Its rules give the same verdicts
   as the `commit-msg` hook from [episode 1](../01-git-github-best-practices/), and a test proves it.

| Path | What it is |
|---|---|
| [`src/team-setup/.vscode/extensions.json`](src/team-setup/.vscode/extensions.json) | `recommendations` + `unwantedRecommendations` (JSON with comments, as VS Code writes it) |
| [`src/team-setup/.vscode/settings.json`](src/team-setup/.vscode/settings.json) | Format on save, LF, per-language default formatter, Git commit-box validation at 72 chars, `mgCommit.scopes` |
| [`src/team-setup/.editorconfig`](src/team-setup/.editorconfig) | Editor-agnostic basics (charset, EOL, indentation) |
| [`src/team-setup/tools/ext_audit.py`](src/team-setup/tools/ext_audit.py) | Audit/installer around `code --list-extensions --show-versions` and `code --install-extension` |
| [`src/mg-commit/package.json`](src/mg-commit/package.json) | Extension manifest: one command, `scm/title` button for Git, two settings, no `activationEvents` |
| [`src/mg-commit/src/commitRules.ts`](src/mg-commit/src/commitRules.ts) | Pure rules (no `vscode` import): `buildHeader`, `validateSubject`, `checkMessage`, `replaceHeader` |
| [`src/mg-commit/src/extension.ts`](src/mg-commit/src/extension.ts) | The command: quick picks + input box, writes into the Git extension's `inputBox` |
| [`src/mg-commit/src/git.d.ts`](src/mg-commit/src/git.d.ts) | The slice of the built-in Git extension API we use (`getAPI(1)`, `repositories`, `inputBox`) |
| [`src/mg-commit/src/test/`](src/mg-commit/src/test/) | 15 `node:test` tests (rules + manifest consistency) |
| [`tests/test_ext_audit.py`](tests/test_ext_audit.py) | 12 pytest tests: JSONC parsing, audit logic, CLI against a fake `code` on `PATH` |
| [`tests/test_rule_parity.py`](tests/test_rule_parity.py) | 30 messages through the TypeScript rules and the episode 1 Python hook: same verdicts |

## Build and test

```bash
cd series/developer-tools/episodes/02-vs-code-extensions/src/mg-commit
npm ci --no-audit --no-fund
npm test                          # tsc + node --test: 15 passed
npx vsce package                  # mg-commit-0.1.0.vsix (8 files, 6.89 KB)

cd ../..                          # episode folder
python3 -m pytest -q tests        # 13 passed (12 audit + 1 parity; parity needs the compiled out/ above)
```

Install and try it (on a desktop with VS Code):

```bash
code --install-extension src/mg-commit/mg-commit-0.1.0.vsix
# or open src/mg-commit in VS Code and press F5 (Extension Development Host)

cd src/team-setup && python3 tools/ext_audit.py            # report, exit 1 if not clean
python3 tools/ext_audit.py --install                        # install missing recommendations
```

The extension's integration with the real VS Code UI (quick picks, Source Control button, writing to the commit box)
is **not** covered by automated tests here: `@vscode/test-electron` downloads VS Code and needs a display, which the
build machine doesn't have. It's verified on a desktop during recording (see [demo.md](demo.md)).

## What we learned / gotchas

- **VS Code's own `extensions.json` isn't JSON.** The template VS Code generates starts with a `//` comment (see
  `extensionsFileTemplate.ts` in the VS Code repo), so `json.load` fails. A regex that strips `//` comments also eats
  `https://` inside strings. `strip_jsonc` walks the text and only removes comments outside strings, plus trailing
  commas; both cases are tested.
- **`vsce package` refuses when `@types/vscode` is newer than `engines.vscode`.** We reproduced it:
  `ERROR @types/vscode ^1.146.0 greater than engines.vscode ^1.100.0`. Pin `@types/vscode` to the oldest VS Code you
  support (`~1.100.0` here); a manifest test guards it.
- **No `activationEvents` needed for commands** since VS Code 1.74: contributing the command is enough. A test fails
  if someone adds them back or lowers `engines.vscode` below 1.74.
- **Recommendations don't block anything.** `unwantedRecommendations` only stops VS Code from suggesting an extension.
  To actually block installs, use `extensions.allowed` (VS Code 1.96+) or the `AllowedExtensions` policy; already
  installed extensions that become disallowed are disabled, not removed.
- **Extension ids are compared case-insensitively** by the audit, because recommendations are usually typed in lower
  case while the CLI listing uses the publisher's casing (e.g. `EditorConfig.EditorConfig`).
- **`node --test out/test/` (a directory) failed on Node 22** with `MODULE_NOT_FOUND`; the script passes the files
  (`out/test/*.test.js`).
- **The Source Control title-bar argument:** when the command runs from the `scm/title` button, the code reads
  `rootUri` from the argument if it is a `Uri`, otherwise it falls back to the single open repo or a picker. Verify on
  the desktop that the button targets the right repo in a multi-root workspace (listed in demo.md).

## References
- [Extension Marketplace](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace) (workspace recommendations, `@recommended`, CLI options, publisher trust in 1.97, extensions have the same permissions as VS Code)
- [Manage extensions in enterprise environments](https://code.visualstudio.com/docs/enterprise/extensions) (`extensions.allowed` from 1.96, `AllowedExtensions` policy)
- [Profiles](https://code.visualstudio.com/docs/configure/profiles) (`--profile`, what a profile contains, export as `.code-profile`)
- [Activation events](https://code.visualstudio.com/api/references/activation-events) (commands need no `onCommand` since 1.74)
- [Publishing extensions](https://code.visualstudio.com/api/working-with-extensions/publishing-extension) (`vsce package`, installing a `.vsix`, `engines.vscode`, pre-release rules)
- VS Code source: [`extensionsFileTemplate.ts`](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/extensions/common/extensionsFileTemplate.ts) (schema of `recommendations` / `unwantedRecommendations`),
  [Git extension API `git.d.ts`](https://github.com/microsoft/vscode/blob/main/extensions/git/src/api/git.d.ts),
  [Git extension `package.json`](https://github.com/microsoft/vscode/blob/main/extensions/git/package.json) (`git.inputValidation*` settings)
- Microsoft Learn: [Live Share extension support](https://learn.microsoft.com/visualstudio/liveshare/reference/extensions) (project-specific vs user-specific extensions)
- Note: VS Code's documentation lives on code.visualstudio.com, not on Microsoft Learn; facts above were checked there.
- Blog: [VS Code Extensions — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-11-25-vs-code-extensions-complete-guide-2025/)
