#!/usr/bin/env bash
# Deletes everything: registry, environment, app, and (if created) the AKS cluster, whose node resource group
# MC_... is deleted with it. Usage: infra/teardown.sh <resource-group> [--aks-only]
set -euo pipefail
RG=${1:?usage: teardown.sh <resource-group> [--aks-only]}
STATE="$HOME/.contoso-orders-containers"
if [ "${2:-}" = "--aks-only" ]; then
  # stop the hourly node charge as soon as the AKS scenes are recorded; Container Apps stays
  az aks delete -g "$RG" -n aks-orders-lab --yes --no-wait
  rm -f "$STATE/aks.json" "$STATE/kubeconfig"
  echo "AKS deletion started. Check: az aks list -g $RG -o table"
  exit 0
fi
az group delete --name "$RG" --yes --no-wait
rm -rf "$STATE"
echo "Deletion of $RG started. Check: az group exists --name $RG (the MC_* node group goes with the cluster)"
