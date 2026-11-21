#!/usr/bin/env bash
# Leave some waste behind on purpose: an unattached static public IP, an empty B1 plan, and two
# unattached disks: one created from an image (has data, billed) and one empty and never used
# (Microsoft Learn: no storage allocated, so no disk charge until first use).
# Usage: infra/deploy-waste-demo.sh <resource-group> [region]
set -euo pipefail
RG=${1:?usage: deploy-waste-demo.sh <resource-group> [region]}
REGION=${2:-swedencentral}
HERE=$(cd "$(dirname "$0")" && pwd)

az group create --name "$RG" --location "$REGION" --tags workload=contoso-waste environment=lab --output none
az deployment group create --resource-group "$RG" --name waste-demo --template-file "$HERE/waste-demo.bicep" --output none
# An OS disk left behind by a deleted VM: created from a Marketplace image, so it holds data
az disk create --resource-group "$RG" --name disk-orphaned-os --sku Standard_LRS \
  --image-reference Canonical:ubuntu-24_04-lts:server:latest --tags workload=contoso-waste --output none
# An empty disk that was never attached
az disk create --resource-group "$RG" --name disk-empty-never-used --sku Standard_LRS --size-gb 32 \
  --tags workload=contoso-waste --output none
az extension add --name resource-graph --upgrade --only-show-errors
az resource list --resource-group "$RG" --query "[].{name:name, type:type}" --output table
