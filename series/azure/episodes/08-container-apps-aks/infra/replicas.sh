#!/usr/bin/env bash
# Replica count per active revision, every 30 s: shows scale-out under load and the scale to zero
# (cool-down 300 s after the last request). Usage: infra/replicas.sh <resource-group> [minutes]
set -euo pipefail
RG=${1:?usage: replicas.sh <resource-group> [minutes]}
MIN=${2:-8}
STATE="$HOME/.contoso-orders-containers"
APP=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["appName"]["value"])' "$STATE/aca.json")
for _ in $(seq 1 $((MIN * 2))); do
  printf '%s  ' "$(date +%H:%M:%S)"
  az containerapp revision list -g "$RG" -n "$APP" --query "[?properties.active].[name, properties.replicas]" -o tsv | tr '\n\t' ' ='
  echo
  sleep 30
done
