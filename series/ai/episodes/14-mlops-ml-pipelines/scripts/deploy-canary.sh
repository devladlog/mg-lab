#!/usr/bin/env bash
# First version: blue with all traffic. Later versions: the other colour with NO traffic, a smoke request to it, then 10 %.
#   RG=... WS=... ENDPOINT_NAME=<unique name> scripts/deploy-canary.sh <model-version>
set -euo pipefail
: "${RG:?}" "${WS:?}" "${ENDPOINT_NAME:?}"
VERSION="${1:?usage: deploy-canary.sh <model-version>}"
MODEL="${MODEL_NAME:-sla-breach}"
az_() { az ml "$@" -g "$RG" -w "$WS"; }

if ! az_ online-endpoint show --name "$ENDPOINT_NAME" >/dev/null 2>&1; then
  az_ online-endpoint create --name "$ENDPOINT_NAME" -f aml/endpoint.yml
  az_ online-deployment create --name blue --endpoint-name "$ENDPOINT_NAME" -f aml/deployment.yml \
    --set name=blue endpoint_name="$ENDPOINT_NAME" model="azureml:$MODEL:$VERSION" --all-traffic
  echo "first deployment: blue serves model version $VERSION"
  exit 0
fi

LIVE="$(az_ online-endpoint show --name "$ENDPOINT_NAME" --query traffic -o json | python3 -c '
import json, sys
t = json.load(sys.stdin)
print(max(t, key=t.get))')"
if [ "$LIVE" = "blue" ]; then NEW=green; else NEW=blue; fi
echo "live: $LIVE, new: $NEW"

az_ online-deployment create --name "$NEW" --endpoint-name "$ENDPOINT_NAME" -f aml/deployment.yml \
  --set name="$NEW" endpoint_name="$ENDPOINT_NAME" model="azureml:$MODEL:$VERSION"
# smoke test the new deployment in isolation (Learn: --deployment-name sends the request to that deployment only)
az_ online-endpoint invoke --name "$ENDPOINT_NAME" --deployment-name "$NEW" --request-file aml/sample-request.json
az_ online-endpoint update --name "$ENDPOINT_NAME" --traffic "$LIVE=90 $NEW=10"
echo "canary: $NEW has 10 % of the traffic. When the numbers hold: scripts/promote.sh $NEW $LIVE"
