#!/usr/bin/env bash
# Runs INSIDE the workload VM (via `az vm run-command invoke`, so no inbound port is needed).
# Usage: vm-check.sh <vault-host>        e.g. kv-mgl09-abc123.vault.azure.net
# Shows four facts: the vault name resolves to a private address, the VM's own identity gets a token,
# that token reads the secret, and nothing can reach the internet.
set -u
host="${1:?usage: vm-check.sh <vault-host>}"

echo "== 1. DNS from inside the network (expect a 10.60.0.x address)"
getent hosts "$host" || echo "no answer"

echo "== 2. token from the VM's managed identity (IMDS, only reachable from this VM)"
token="$(curl -s --max-time 10 -H 'Metadata: true' \
  'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')"
[ -n "$token" ] && echo "got a token (${#token} characters, not printed)" || { echo "no token"; exit 1; }

echo "== 3. read the secret through the private endpoint (expect HTTP 200)"
code="$(curl -s --max-time 15 -o /tmp/secret.json -w '%{http_code}' \
  -H "Authorization: Bearer $token" "https://$host/secrets/demo-secret?api-version=7.4")"
echo "HTTP $code"
python3 -c 'import json; print("secret id:", json.load(open("/tmp/secret.json")).get("id", "n/a"))' 2>/dev/null
rm -f /tmp/secret.json

echo "== 4. the internet (expect no route: timeout or failure, code 000)"
curl -s --max-time 8 -o /dev/null -w 'HTTP %{http_code}\n' https://example.com || echo "no route (expected)"
