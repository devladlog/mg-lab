#!/usr/bin/env bash
# Deletes the resource group (gateway, public IP, VM, VNets) and the local state. The gateway bills by the hour.
# Usage: infra/teardown.sh <resource-group>
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group>}
az group delete --name "$RG" --yes --no-wait
rm -rf "$HOME/.contoso-net"
echo "Deletion of $RG started. Check: az group exists --name $RG   (false when done)"
