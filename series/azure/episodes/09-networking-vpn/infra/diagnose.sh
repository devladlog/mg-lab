#!/usr/bin/env bash
# Network Watcher checks against the spoke VM: which NSG rule decides, and where the next hop goes.
# Usage: infra/diagnose.sh <resource-group> <vpn-client-ip> [lab-server-ip]
#   vpn-client-ip : the address probe.py printed as "client" (an address from the P2S pool)
#   lab-server-ip : an address that is NOT on the VPN (default 10.50.0.22, CON-SRV02)
set -euo pipefail
RG=${1:?usage: diagnose.sh <resource-group> <vpn-client-ip> [lab-server-ip]}
CLIENT=${2:?need the vpn client ip}
LAB=${3:-10.50.0.22}
VM=vm-orders-int
VMIP=$(jq -r '.vmPrivateIp.value' "$HOME/.contoso-net/outputs.json")

echo "== IP flow verify, inbound TCP 8080 from the VPN client ($CLIENT)"
az network watcher test-ip-flow -g "$RG" --vm "$VM" --direction Inbound --protocol TCP \
  --local "$VMIP:8080" --remote "$CLIENT:50000" --query "{access:access, rule:ruleName}" -o table
echo "== IP flow verify, inbound TCP 8080 from a lab server that is not on the VPN ($LAB)"
az network watcher test-ip-flow -g "$RG" --vm "$VM" --direction Inbound --protocol TCP \
  --local "$VMIP:8080" --remote "$LAB:50000" --query "{access:access, rule:ruleName}" -o table
echo "== Next hop from the VM to the VPN client"
az network watcher show-next-hop -g "$RG" --vm "$VM" --source-ip "$VMIP" --dest-ip "$CLIENT" \
  --query "{type:nextHopType, ip:nextHopIpAddress, route:routeTableId}" -o table
echo "== Next hop from the VM to the lab server (no site-to-site yet: expect None)"
az network watcher show-next-hop -g "$RG" --vm "$VM" --source-ip "$VMIP" --dest-ip "$LAB" \
  --query "{type:nextHopType, ip:nextHopIpAddress, route:routeTableId}" -o table
