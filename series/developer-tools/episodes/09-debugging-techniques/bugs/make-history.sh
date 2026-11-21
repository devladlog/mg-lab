#!/usr/bin/env bash
# Builds a throwaway repository with a history for the git bisect demo:
#   7 commits, the report is correct in the first one, "refactor(reports): compute the last day of the month once"
#   (bugs/01-month-end-off-by-one.patch) is the fourth, and everything after it carries the bug.
# Usage: bugs/make-history.sh <empty-or-new-folder>      then:  cd <folder>; git bisect start HEAD demo-good
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
dest="${1:?usage: make-history.sh <empty-or-new-folder>}"
if [[ -d "$dest" && -n "$(ls -A "$dest")" ]]; then
    echo "make-history: $dest is not empty" >&2
    exit 2
fi
mkdir -p "$dest"
(cd "$here/../src/orders-app" && tar cf - --exclude=bin --exclude=obj --exclude=triage --exclude='*.db*' .) | tar xf - -C "$dest"
cd "$dest"

g() { git -c user.name="Alex Demo" -c user.email="alex.demo@contoso.example" -c commit.gpgsign=false -c core.autocrlf=false "$@"; }
note() { printf '\n// %s\n' "$2" >> "$1"; }

git init -q -b main
g add -A
g commit -q -m "feat(reports): monthly revenue per customer"
git tag demo-good

note src/Contoso.Orders.Api/Orders.cs "paging rules are shared by every list endpoint"
g commit -qam "docs(orders): say where the paging rules apply"
note src/Contoso.Orders.Api/Program.cs "the report cache is one per process"
g commit -qam "docs(api): note the report cache lifetime"

g apply --ignore-whitespace "$here/01-month-end-off-by-one.patch"
g commit -qam "refactor(reports): compute the last day of the month once"

note src/Contoso.Orders.Api/Orders.cs "seed data is deterministic"
g commit -qam "docs(orders): mention the seed"
note src/Contoso.Orders.Api/Program.cs "health check reports the build"
g commit -qam "docs(api): mention the version in /healthz"
g commit -q --allow-empty -m "chore: release 2026.11"

echo "history built in $dest: $(git rev-list --count HEAD) commits, good = demo-good, bad = HEAD"
