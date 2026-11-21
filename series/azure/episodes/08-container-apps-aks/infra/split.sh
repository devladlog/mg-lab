#!/usr/bin/env bash
# Sends N requests to GET / and counts which version answered. Usage: infra/split.sh <url> [requests]
set -euo pipefail
URL=${1:?usage: split.sh <url> [requests]}
N=${2:-100}
for _ in $(seq 1 "$N"); do
  curl -fsS "$URL/" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])'
done | sort | uniq -c | awk -v n="$N" '{ printf "  %-8s %4d  (%d %%)\n", $2, $1, ($1 * 100 + n / 2) / n }'
