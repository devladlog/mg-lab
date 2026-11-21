#!/usr/bin/env bash
# Deploys the hub-and-spoke + point-to-site VPN into one resource group.
# Usage: infra/deploy.sh <resource-group> [location]      (needs `az login`; Owner or Contributor on the subscription)
# The VPN gateway is the slow part: Learn says gateway creation can take 45 minutes or more.
set -euo pipefail
RG=${1:?usage: deploy.sh <resource-group> [location]}
LOC=${2:-westeurope}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-net"
mkdir -p "$STATE"

echo "== 1/5 address plan (no Azure call)"
python3 "$HERE/../src/netplan/netplan.py" check "$HERE/../src/netplan/plan.json"
python3 "$HERE/../src/netplan/netplan.py" params "$HERE/../src/netplan/plan.json" > "$STATE/params.json"

echo "== 2/5 certificates and a throwaway SSH key (kept in $STATE, never in the repo)"
[ -f "$STATE/certs/rootCert.b64" ] || "$HERE/certs.sh" "$STATE/certs" labadmin
[ -f "$STATE/vm_key" ] || ssh-keygen -q -t ed25519 -N "" -C "contoso-net-lab" -f "$STATE/vm_key"

echo "== 3/5 resource group"
az group create --name "$RG" --location "$LOC" --tags workload=contoso-orders environment=lab -o none

PARAMS=(--parameters "@$STATE/params.json"
        --parameters "p2sRootCertData=$(tr -d '\n' < "$STATE/certs/rootCert.b64")"
        --parameters "sshPublicKey=$(cat "$STATE/vm_key.pub")")

echo "== 4/5 what-if (creates nothing)"
az deployment group what-if --resource-group "$RG" --template-file "$HERE/main.bicep" "${PARAMS[@]}" --no-pretty-print \
  --query "properties.changes[].{op:changeType, resource:resourceId}" -o table

echo "== 5/5 deploy (gateway: 45 minutes or more)"
az deployment group create --resource-group "$RG" --name net09 --template-file "$HERE/main.bicep" "${PARAMS[@]}" \
  --query "properties.outputs" -o json | tee "$STATE/outputs.json"
