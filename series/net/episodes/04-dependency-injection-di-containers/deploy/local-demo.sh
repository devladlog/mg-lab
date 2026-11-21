#!/usr/bin/env bash
# The DI walk-through from the video, against the API started with `dotnet run` (Development).
#
#   ./deploy/local-demo.sh                 # http://localhost:5207
#   ./deploy/local-demo.sh https://<host>  # /diagnostics/lifetimes only exists in Development
#
# Needs curl and jq.
set -euo pipefail

BASE="${1:-http://localhost:5207}"
step() { printf '\n== %s\n' "$*"; }

step "1. Lifetimes: two requests to the same endpoint"
for i in 1 2; do
  curl -fsS "$BASE/diagnostics/lifetimes" \
    | jq -c '{endpoint: .endpoint, consumer: .consumer}' \
    || echo "(not available: Development only)"
done

step "2. Two requests waiting for a decision"
for dept in FIN OPS; do
  curl -fsS -H "Content-Type: application/json" -X POST "$BASE/api/requests" \
    --data "{\"title\":\"Laptop refresh\",\"budget\":12000,\"requestedBy\":\"alex.demo@contoso.com\",\"departmentCode\":\"$dept\"}" \
    | jq -c '{id, department, status}'
done

step "3. Send the digest now (request scope, configured channel)"
curl -fsS -X POST "$BASE/api/digest/send" | jq -c '{channel, sent, total: (.digest.lines | map(.requests) | add), lines: .digest.lines}'
