#!/usr/bin/env bash
# Deletes everything the episode created (alerts, web test and action group live in the group too).
# Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
az group delete --name "$RG" --yes --no-wait
rm -f "$HOME/.contoso-orders-monitoring/outputs.json"
echo "Deletion of $RG started. Check: az group exists --name $RG"
