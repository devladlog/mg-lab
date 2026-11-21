#!/usr/bin/env bash
# Local walk-through with real JWTs from `dotnet user-jwts` (no tenant needed).
# Start the API first:  dotnet run --project src/ExpenseClaims.Api --launch-profile http
#   ./deploy/local-demo.sh [http://localhost:5252]
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="$here/../src/ExpenseClaims.Api"
base="${1:-http://localhost:5252}"
json=(-H "Content-Type: application/json")
today="$(date -u +%F)"

step() { printf '\n\033[1m# %s\033[0m\n' "$*"; }
call() { curl -sS -w '\n<- HTTP %{http_code}\n' "$@"; }

step "Tokens: Alex is an employee, Sam has the Claims.Approve app role"
# --claim roles=... (not --role): the API reads the Entra-style "roles" claim; --role writes "role".
alex="$(dotnet user-jwts create --project "$project" --name alex.demo -o token)"
sam="$(dotnet user-jwts create --project "$project" --name sam.approver --claim roles=Claims.Approve -o token)"
echo "alex: ${alex:0:24}...   sam: ${sam:0:24}..."

# The API reads the user-jwts signing key from user secrets at startup. If the very first token was created
# after `dotnet run` started, every token is rejected: restart the API once.
if [[ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $alex" "$base/api/claims")" != "200" ]]; then
  echo "Token rejected. The signing key didn't exist when the API started: restart 'dotnet run' and run this again." >&2
  exit 1
fi

step "1. No token -> 401"
curl -sS -o /dev/null -D - "$base/api/claims" | grep -Ei '^(HTTP|WWW-Authenticate)'

step "2. Invalid claim -> automatic 400 from [ApiController]"
call -X POST "$base/api/claims" "${json[@]}" -H "Authorization: Bearer $alex" \
  -d '{"description":"x","amount":0,"currency":"eur","category":"Party"}'

step "3. Alex submits a claim -> 201 Created + Location"
created="$(curl -sS -D /tmp/claims-headers.txt -X POST "$base/api/claims" "${json[@]}" -H "Authorization: Bearer $alex" \
  -d "{\"description\":\"Train to Porto\",\"amount\":48.50,\"currency\":\"EUR\",\"category\":\"Travel\",\"incurredOn\":\"$today\"}")"
grep -Ei '^(HTTP|Location)' /tmp/claims-headers.txt
echo "$created"
id="$(sed -E 's/.*"id":([0-9]+).*/\1/' <<<"$created")"

step "4. Alex tries to approve -> 403 (no Claims.Approve role)"
call -X POST "$base/api/claims/$id/approve" -H "Authorization: Bearer $alex"

step "5. Sam approves -> 200"
call -X POST "$base/api/claims/$id/approve" -H "Authorization: Bearer $sam"

step "6. Sam approves again -> 409 problem details from the exception handler"
call -X POST "$base/api/claims/$id/approve" -H "Authorization: Bearer $sam"

step "7. Five more submits -> 429: limit is 5 per user per minute, and the 400 from step 2 counted too"
for _ in 1 2 3 4 5; do
  curl -sS -o /dev/null -w '%{http_code} ' -X POST "$base/api/claims" "${json[@]}" -H "Authorization: Bearer $alex" \
    -d "{\"description\":\"Lunch with client\",\"amount\":18,\"currency\":\"EUR\",\"category\":\"Meals\",\"incurredOn\":\"$today\"}"
done
echo
dotnet user-jwts clear --project "$project" --force >/dev/null
