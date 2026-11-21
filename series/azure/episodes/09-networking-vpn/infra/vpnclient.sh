#!/usr/bin/env bash
# Generates and downloads the VPN client profile package. Run it again after ANY change to peering or topology:
# Learn: Windows clients must download and install the package again for route changes to apply.
# Usage: infra/vpnclient.sh <resource-group> [gateway-name]
set -euo pipefail
RG=${1:?usage: vpnclient.sh <resource-group> [gateway-name]}
GW=${2:-vgw-hub}
STATE="$HOME/.contoso-net"
mkdir -p "$STATE/client"
URL=$(az network vnet-gateway vpn-client generate --resource-group "$RG" --name "$GW" --processor-architecture Amd64 -o tsv)
curl -fsSL -o "$STATE/client/vpnclient.zip" "$URL"
rm -rf "$STATE/client/unzipped" && unzip -q "$STATE/client/vpnclient.zip" -d "$STATE/client/unzipped"
echo "package: $STATE/client/vpnclient.zip"
(cd "$STATE/client/unzipped" && find . -type f | sort)
