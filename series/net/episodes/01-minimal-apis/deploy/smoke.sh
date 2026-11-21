#!/usr/bin/env bash
# Walk through the API like the video does. Works against localhost or the App Service URL.
#   ./deploy/smoke.sh http://localhost:5207
#   ./deploy/smoke.sh https://<app>.azurewebsites.net
set -euo pipefail
base="${1:?usage: smoke.sh <base-url>}"
json=(-H "Content-Type: application/json")

step() { printf '\n\033[1m# %s\033[0m\n' "$*"; }
call() { curl -sS -w '\n<- HTTP %{http_code}\n' "$@"; }

step "1. Invalid body -> 400 validation problem"
call -X POST "$base/api/requests" "${json[@]}" -d '{"title":"x","budget":0,"requestedBy":"not-an-email"}'

step "2. 300k without justification -> 400 (cross-field rule)"
call -X POST "$base/api/requests" "${json[@]}" \
  -d '{"title":"Data platform","budget":300000,"requestedBy":"alex.demo@contoso.com"}'

step "3. Valid request, 75k -> 201 Created, priority High"
created="$(curl -sS -X POST "$base/api/requests" "${json[@]}" \
  -d '{"title":"CRM rollout","budget":75000,"requestedBy":"alex.demo@contoso.com"}')"
echo "$created"
id="$(sed -E 's/.*"id":([0-9]+).*/\1/' <<<"$created")"

step "4. Approve your own request -> 409"
call -X POST "$base/api/requests/$id/decision" "${json[@]}" \
  -d '{"approve":true,"decidedBy":"Alex.Demo@contoso.com"}'

step "5. Approver decides -> 200 Approved"
call -X POST "$base/api/requests/$id/decision" "${json[@]}" \
  -d '{"approve":true,"decidedBy":"sam.approver@contoso.com"}'

step "6. Unknown id -> 404 problem details"
call "$base/api/requests/9999"

step "7. High-priority list"
call "$base/api/requests?priority=High"
