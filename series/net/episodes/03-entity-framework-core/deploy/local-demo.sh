#!/usr/bin/env bash
# The lost-update story from the video, against any base URL (local SQLite or Azure SQL behind App Service).
#
#   ./deploy/local-demo.sh                          # http://localhost:5207
#   ./deploy/local-demo.sh https://<app-host>
#
# Needs curl and jq. Creates one request per run (the database keeps them: that's the point of this episode).
set -euo pipefail

BASE="${1:-http://localhost:5207}"
api="$BASE/api/requests"
json=(-H "Content-Type: application/json")

step() { printf '\n== %s\n' "$*"; }
call() {  # call METHOD URL [BODY] -> prints "<- HTTP nnn" and the body, leaves the body in $body
  local method="$1" url="$2" data="${3:-}" out code
  out="$(mktemp)"
  if [[ -n "$data" ]]; then
    code="$(curl -sS -o "$out" -w '%{http_code}' -X "$method" "${json[@]}" --data "$data" "$url")"
  else
    code="$(curl -sS -o "$out" -w '%{http_code}' -X "$method" "$url")"
  fi
  body="$(cat "$out")"; rm -f "$out"
  echo "<- HTTP $code"
  if [[ -n "$body" ]]; then jq -c . <<<"$body" 2>/dev/null || echo "$body"; fi
}

step "1. Alex submits a 40,000 request for Finance"
call POST "$api" '{"title":"Laptop refresh","budget":40000,"requestedBy":"alex.demo@contoso.com","departmentCode":"fin"}'
id="$(jq -r .id <<<"$body")"

step "2. Sam (approver) opens it and sees version A"
call GET "$api/$id"
versionA="$(jq -r .version <<<"$body")"
echo "   Sam sees budget $(jq -r .budget <<<"$body"), version ${versionA:0:8}..."

step "3. Meanwhile Alex raises the budget to 400,000 (with a justification)"
call PUT "$api/$id/budget" "{\"budget\":400000,\"justification\":\"Scope grew to all sites.\",\"version\":\"$versionA\"}"
echo "   new version $(jq -r .version <<<"$body" | cut -c1-8)..., priority $(jq -r .priority <<<"$body")"

step "4. Sam clicks Approve on what he saw (version A)"
call POST "$api/$id/decision" "{\"approve\":true,\"decidedBy\":\"sam.approver@contoso.com\",\"version\":\"$versionA\"}"

step "5. Sam reads it again: 400,000, still Submitted. Approves the current version"
call GET "$api/$id"
versionB="$(jq -r .version <<<"$body")"
call POST "$api/$id/decision" "{\"approve\":true,\"decidedBy\":\"sam.approver@contoso.com\",\"version\":\"$versionB\"}"

step "6. Totals per department, computed by the database"
call GET "$api/summary"
