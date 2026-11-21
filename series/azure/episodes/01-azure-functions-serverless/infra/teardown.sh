#!/usr/bin/env bash
# Deletes everything the episode created. Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
az group delete --name "$RG" --yes --no-wait
echo "Deletion of $RG started. Check: az group exists --name $RG"
