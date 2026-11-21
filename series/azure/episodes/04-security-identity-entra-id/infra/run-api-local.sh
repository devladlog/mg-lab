#!/usr/bin/env bash
# Run the orders API on this machine against the real tenant (Entra token validation, no secrets in config).
# Usage: infra/run-api-local.sh [port]      (reads ~/.contoso-orders/outputs.json from deploy.sh)
set -euo pipefail
PORT=${1:-5080}
OUT=${OUT:-$HOME/.contoso-orders}
HERE=$(cd "$(dirname "$0")" && pwd)
get() { python3 -c "import json;print(json.load(open('$OUT/outputs.json'))['$1'])"; }

export AzureAd__TenantId=$(get tenantId)
export AzureAd__ClientId=$(get apiClientId)
exec dotnet run --project "$HERE/../src/Contoso.Orders.Api" --urls "http://localhost:$PORT"
