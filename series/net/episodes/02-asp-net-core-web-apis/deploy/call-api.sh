#!/usr/bin/env bash
# Call the deployed API with a real Microsoft Entra access token from the Azure CLI.
# Prerequisites (see demo.md): the API app registration exposes the Claims.Submit scope, lists the Azure CLI
# (04b07795-8ddb-461a-bbee-02f9e1bf7b46) under "Authorized client applications", and the signed-in user
# may have the Claims.Approve app role.
#
#   ./deploy/call-api.sh https://<app>.azurewebsites.net <api-client-id> [claim-id-to-approve]
set -euo pipefail
base="${1:?usage: call-api.sh <base-url> <api-client-id> [claim-id]}"
client_id="${2:?usage: call-api.sh <base-url> <api-client-id> [claim-id]}"
approve_id="${3:-}"

token="$(az account get-access-token --scope "api://$client_id/Claims.Submit" --query accessToken -o tsv)"

# Show the claims the API cares about (decode the JWT payload, base64url -> base64).
payload="$(cut -d. -f2 <<<"$token" | tr '_-' '/+')"
while (( ${#payload} % 4 )); do payload+="="; done
base64 -d <<<"$payload" | jq '{aud, iss, ver, scp, roles, oid: (.oid[0:8] + "...")}'

auth=(-H "Authorization: Bearer $token")
today="$(date -u +%F)"

echo "# POST /api/claims"
curl -sS -w '\n<- HTTP %{http_code}\n' -X POST "$base/api/claims" "${auth[@]}" -H "Content-Type: application/json" \
  -d "{\"description\":\"Train to Porto\",\"amount\":48.50,\"currency\":\"EUR\",\"category\":\"Travel\",\"incurredOn\":\"$today\"}"

if [[ -n "$approve_id" ]]; then
  echo "# POST /api/claims/$approve_id/approve"
  curl -sS -w '\n<- HTTP %{http_code}\n' -X POST "$base/api/claims/$approve_id/approve" "${auth[@]}"
fi
