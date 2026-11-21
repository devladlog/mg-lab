#!/usr/bin/env bash
# One-time setup after cloning. Hooks are not copied by `git clone`, so every developer runs this once.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

command -v python3 >/dev/null || { echo "python3 is required for the hooks" >&2; exit 1; }

git config core.hooksPath .githooks   # versioned hooks instead of .git/hooks
git config fetch.prune true           # drop remote branches that were deleted after merge
git config pull.ff only               # never create surprise merge commits on pull
git config push.autoSetupRemote true  # first push of a new branch sets its upstream

chmod +x .githooks/* 2>/dev/null || true
echo "Hooks: $(git config core.hooksPath)  |  fetch.prune=$(git config fetch.prune)  pull.ff=$(git config pull.ff)"
