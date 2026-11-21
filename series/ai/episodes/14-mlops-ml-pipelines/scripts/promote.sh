#!/usr/bin/env bash
# Move all traffic to the canary, then delete the old deployment (it costs money while it exists).
#   RG=... WS=... ENDPOINT_NAME=... scripts/promote.sh <new-deployment> <old-deployment>
set -euo pipefail
: "${RG:?}" "${WS:?}" "${ENDPOINT_NAME:?}"
NEW="${1:?new deployment}"; OLD="${2:?old deployment}"
az ml online-endpoint update --name "$ENDPOINT_NAME" --traffic "$OLD=0 $NEW=100" -g "$RG" -w "$WS"
az ml online-deployment delete --name "$OLD" --endpoint-name "$ENDPOINT_NAME" --yes --no-wait -g "$RG" -w "$WS"
echo "$NEW serves everything; $OLD is being deleted"
