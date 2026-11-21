#!/usr/bin/env bash
# Create or update a repository ruleset from a JSON file (idempotent: matched by name).
# Usage:  scripts/apply-ruleset.sh OWNER/REPO [.github/rulesets/protect-main.json]
# Needs:  gh CLI signed in (gh auth login) as a repo admin. Rulesets need a public repo on GitHub Free,
#         or GitHub Pro / Team / Enterprise for private repos.
set -euo pipefail

repo="${1:?usage: apply-ruleset.sh OWNER/REPO [ruleset.json]}"
file="${2:-.github/rulesets/protect-main.json}"
[[ -f "$file" ]] || { echo "ruleset file not found: $file" >&2; exit 1; }

name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"
api=(gh api -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")

id="$("${api[@]}" "repos/$repo/rulesets?includes_parents=false" \
        --jq ".[] | select(.name == \"$name\") | .id" | head -n 1)"

if [[ -n "$id" ]]; then
  "${api[@]}" --method PUT "repos/$repo/rulesets/$id" --input "$file" \
    --jq '"updated ruleset \(.id) \(.name) (\(.enforcement))"'
else
  "${api[@]}" --method POST "repos/$repo/rulesets" --input "$file" \
    --jq '"created ruleset \(.id) \(.name) (\(.enforcement))"'
fi
