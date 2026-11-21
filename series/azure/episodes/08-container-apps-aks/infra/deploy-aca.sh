#!/usr/bin/env bash
# Phase 1: registry + environment. Phase 2: push 1.0.0, then create the container app.
# Needs: az (signed in, containerapp extension), dotnet 10. Usage: infra/deploy-aca.sh <resource-group> [region]
set -euo pipefail
RG=${1:?usage: deploy-aca.sh <resource-group> [region]}
REGION=${2:-westeurope}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-orders-containers"; mkdir -p "$STATE"
export PUSHER_OBJECT_ID=${PUSHER_OBJECT_ID:-$(az ad signed-in-user show --query id -o tsv)}
out() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]["value"])' "$STATE/aca.json" "$1"; }

az extension add --name containerapp --upgrade --only-show-errors
# a fresh pay-as-you-go subscription has not used these resource providers yet; registering is idempotent
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.OperationalInsights Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns" --wait --only-show-errors
done
az group create --name "$RG" --location "$REGION" --tags workload=contoso-orders environment=lab --output none

echo "== phase 1: registry, identity, environment"
DEPLOY_APP=false az deployment group create -g "$RG" -n aca-base --parameters "$HERE/aca.bicepparam" \
  --query properties.outputs -o json > "$STATE/aca.json"
ACR=$(out acrName)

echo "== push 1.0.0"
"$HERE/push-image.sh" "$ACR" 1.0.0

echo "== phase 2: what-if, then the app"
export DEPLOY_APP=true IMAGE_TAG=1.0.0 REVISION_SUFFIX=v1-0-0
az deployment group what-if -g "$RG" --parameters "$HERE/aca.bicepparam"
az deployment group create -g "$RG" -n aca-app --parameters "$HERE/aca.bicepparam" \
  --query properties.outputs -o json > "$STATE/aca.json"
URL=$(out appUrl)
echo "$URL" > "$STATE/url"
for i in $(seq 1 30); do
  if curl -fsS "$URL/"; then echo; echo "App: $URL"; exit 0; fi
  sleep 10
done
echo "App did not answer in 5 minutes" >&2; exit 1
