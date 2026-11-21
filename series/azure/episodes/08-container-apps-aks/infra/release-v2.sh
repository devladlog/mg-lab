#!/usr/bin/env bash
# Pushes 1.1.0, creates a second revision next to v1-0-0, waits until it's ready, then sends it 20 % of traffic.
# Usage: infra/release-v2.sh <resource-group> [percent-to-v2]
set -euo pipefail
RG=${1:?usage: release-v2.sh <resource-group> [percent]}
PCT=${2:-20}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-orders-containers"
out() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]["value"])' "$STATE/aca.json" "$1"; }
ACR=$(out acrName); APP=$(out appName); LOGIN=$(out acrLoginServer)

"$HERE/push-image.sh" "$ACR" 1.1.0

# The app's traffic rule is "latest revision, 100 %": a new revision would take everything the moment it is ready.
# Pin v1-0-0 to 100 % first (Learn: "Update existing revision"), so v1-1-0 starts at 0 % and we choose when it gets traffic.
V1="$APP--v1-0-0"; V2="$APP--v1-1-0"
az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$V1=100" --output none

echo "== new revision (multiple revision mode: v1-0-0 keeps running)"
az containerapp update -g "$RG" -n "$APP" --image "$LOGIN/contoso/orders-api:1.1.0" --revision-suffix v1-1-0 --output none
for i in $(seq 1 30); do
  state=$(az containerapp revision show -g "$RG" -n "$APP" --revision "$V2" --query properties.provisioningState -o tsv)
  echo "  $V2: $state"
  [ "$state" = Provisioned ] && break
  sleep 10
done

echo "== traffic: $((100 - PCT)) % v1.0.0, $PCT % v1.1.0"
az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$V1=$((100 - PCT))" "$V2=$PCT" -o table
az containerapp revision list -g "$RG" -n "$APP" \
  --query "[].{revision:name, active:properties.active, traffic:properties.trafficWeight, replicas:properties.replicas, state:properties.runningState}" -o table
