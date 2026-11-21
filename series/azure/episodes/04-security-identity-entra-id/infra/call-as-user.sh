#!/usr/bin/env bash
# Call the API (running locally, see README) as yourself through the Azure CLI: GET is allowed, POST is not.
# Prints the token's authorization claims, never the token.
# Usage: infra/call-as-user.sh [api-base-url]       (default http://localhost:5080)
set -euo pipefail
BASE=${1:-http://localhost:5080}
OUT=${OUT:-$HOME/.contoso-orders}
HERE=$(cd "$(dirname "$0")" && pwd)

SCOPE=$(python3 -c "import json;print(json.load(open('$OUT/outputs.json'))['readScope'])")
TOKEN=$(az account get-access-token --scope "$SCOPE" --query accessToken --output tsv)

echo "== token claims (delegated)"
printf '%s' "$TOKEN" | python3 "$HERE/../tools/claims.py"

call() {  # call METHOD PATH [JSON-BODY]
  local args=(-s -o "$BODY" -w '%{http_code}' -X "$1" "$BASE$2" -H "Authorization: Bearer $TOKEN")
  [[ $# -eq 3 ]] && args+=(-H 'Content-Type: application/json' --data "$3")
  echo "== $1 $2 -> $(curl "${args[@]}")"
  cat "$BODY"; echo
}
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT
call GET /orders
call GET /me
call POST /orders '{"customer":"Alex Demo","sku":"ABC-123","quantity":1}'     # expect 403: users can't write
