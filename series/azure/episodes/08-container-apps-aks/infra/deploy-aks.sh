#!/usr/bin/env bash
# The same 1.0.0 image on AKS (Free tier, one node). Run AFTER deploy-aca.sh (it reuses the registry).
# Needs: az, kubectl (az aks install-cli). Usage: infra/deploy-aks.sh <resource-group>
set -euo pipefail
RG=${1:?usage: deploy-aks.sh <resource-group>}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-orders-containers"
out() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]["value"])' "$STATE/$1.json" "$2"; }
export ACR_NAME; ACR_NAME=$(out aca acrName)
LOGIN=$(out aca acrLoginServer)

az provider register --namespace Microsoft.ContainerService --wait --only-show-errors
# the node needs 4 vCPUs of the Standard DASv5 family in the group's region: stop early instead of failing mid-deployment
REGION=$(az group show -n "$RG" --query location -o tsv) || true
read -r USED LIMIT < <(az vm list-usage -l "$REGION" --query "[?name.value=='standardDASv5Family'].[currentValue,limit]" -o tsv) || true
echo "DASv5 vCPU quota in $REGION: $USED of $LIMIT used"
[ $(( ${LIMIT:-0} - ${USED:-0} )) -ge 4 ] || { echo "Not enough DASv5 vCPU quota for Standard_D4as_v5 (needs 4)" >&2; exit 1; }

echo "== AKS cluster (about 5-10 minutes); the clock for the node starts now"
az deployment group create -g "$RG" -n aks --parameters "$HERE/aks.bicepparam" --query properties.outputs -o json > "$STATE/aks.json"
CLUSTER=$(out aks clusterName)
az aks get-credentials -g "$RG" -n "$CLUSTER" --overwrite-existing --file "$STATE/kubeconfig"
export KUBECONFIG="$STATE/kubeconfig"

echo "== manifests (server-side dry run first)"
RENDERED=$(mktemp -d); trap 'rm -rf "$RENDERED"' EXIT
for f in "$HERE"/../k8s/*.yaml; do
  sed -e "s|ACR_LOGIN_SERVER|$LOGIN|" -e "s|IMAGE_TAG|1.0.0|" "$f" > "$RENDERED/$(basename "$f")"
done
kubectl apply --dry-run=server -f "$RENDERED"
kubectl apply -f "$RENDERED"
kubectl rollout status deployment/orders-api --timeout=180s

for i in $(seq 1 30); do
  IP=$(kubectl get service orders-api -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
  [ -n "$IP" ] && break; sleep 10
done
kubectl get nodes,pods,svc,hpa -o wide
curl -fsS "http://$IP/"; echo
