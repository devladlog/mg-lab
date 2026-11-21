#!/usr/bin/env bash
# Runs the API on this machine against the Azure resources from deploy.sh, as the az-login identity
# (DefaultAzureCredential -> AzureCliCredential). Usage: infra/run-api.sh [port]
set -euo pipefail
PORT=${1:-5199}
HERE=$(cd "$(dirname "$0")" && pwd)
STATE="$HOME/.contoso-orders-data/outputs.json"
[ -f "$STATE" ] || { echo "Run infra/deploy.sh first ($STATE not found)" >&2; exit 1; }
out() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]["value"])' "$STATE" "$1"; }

export Database__Provider=SqlServer
export Database__Server; Database__Server=$(out sqlServerFqdn)
export Database__Database; Database__Database=$(out databaseName)
export Invoices__BlobServiceUri; Invoices__BlobServiceUri=$(out blobServiceUri)
exec dotnet run --project "$HERE/../src/Contoso.Orders.Api" --urls "http://localhost:$PORT"
