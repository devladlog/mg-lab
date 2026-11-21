#!/usr/bin/env bash
# Squash-only merges whose commit message is the PR title + body, and auto-delete merged branches.
# Usage:  scripts/configure-repo.sh OWNER/REPO      (gh CLI signed in as a repo admin)
set -euo pipefail

repo="${1:?usage: configure-repo.sh OWNER/REPO}"

gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" \
  --method PATCH "repos/$repo" \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY \
  --jq '"\(.full_name): squash=\(.allow_squash_merge) merge=\(.allow_merge_commit) rebase=\(.allow_rebase_merge) delete_branch_on_merge=\(.delete_branch_on_merge) title=\(.squash_merge_commit_title)"'
