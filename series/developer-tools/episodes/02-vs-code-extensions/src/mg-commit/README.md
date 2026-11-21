# MG Commit Helper

Compose a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) message without leaving the
Source Control view: type → scope → breaking? → subject, validated as you type (lower-case verb, no period,
72-character header). The header goes into the commit box; any body you already wrote is kept.

- **Command:** `MG: Compose Conventional Commit` (Command Palette, or the pencil icon in the Source Control title bar)
- **Settings:** `mgCommit.types`, `mgCommit.scopes` (put the scopes in the repo's `.vscode/settings.json`)

The rules match the `commit-msg` hook from DEVLADLOG Dev Tools episode 1, so a message built here passes the hook.
