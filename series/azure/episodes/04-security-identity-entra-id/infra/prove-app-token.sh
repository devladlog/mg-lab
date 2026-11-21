#!/usr/bin/env bash
# Prove the managed identity gets an app-only token with the Orders.ReadWrite.All role, without any secret:
# a short-lived Azure Container Instance runs tools/claims.py against the instance metadata service (IMDS)
# as the order processor's user-assigned identity, prints the claims (not the token), and is deleted.
# Usage: infra/prove-app-token.sh <resource-group>
set -euo pipefail
RG=${1:?usage: prove-app-token.sh <resource-group>}
OUT=${OUT:-$HOME/.contoso-orders}
HERE=$(cd "$(dirname "$0")" && pwd)
get() { python3 -c "import json;print(json.load(open('$OUT/outputs.json'))['$1'])"; }

NAME=aci-contoso-token-proof
CODE=$(base64 -w0 "$HERE/../tools/claims.py")
# The container gets the script as base64 in an environment variable: no quoting problems, nothing to build.
az container create --resource-group "$RG" --name "$NAME" \
  --image mcr.microsoft.com/azure-cli --os-type Linux --cpu 1 --memory 1 --restart-policy Never \
  --assign-identity "$(get processorResourceId)" \
  --environment-variables CODE="$CODE" RES="$(get apiAppIdUri)" CID="$(get processorClientId)" \
  --command-line "python3 -c \"import base64,os,sys;sys.argv=['claims','--imds',os.environ['RES'],os.environ['CID']];exec(base64.b64decode(os.environ['CODE']))\"" \
  --output none

for _ in $(seq 1 30); do
  state=$(az container show --resource-group "$RG" --name "$NAME" --query "containers[0].instanceView.currentState.state" --output tsv)
  [[ "$state" == "Terminated" ]] && break
  sleep 5
done
echo "== claims of the managed identity's token (expect aud = API client ID, roles = Orders.ReadWrite.All, idtyp = app)"
az container logs --resource-group "$RG" --name "$NAME"
az container delete --resource-group "$RG" --name "$NAME" --yes --output none
