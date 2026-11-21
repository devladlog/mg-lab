#!/usr/bin/env bash
# Turn fault injection on or off in Azure: a share of saves throws (HTTP 500).
# Changing an app setting restarts the app. Usage: infra/chaos.sh <rg> <failure-percent 0-100>
set -euo pipefail
RG=${1:?usage: chaos.sh <resource-group> <failure-percent>}
PCT=${2:?usage: chaos.sh <resource-group> <failure-percent>}
[[ "$PCT" =~ ^([0-9]|[1-9][0-9]|100)$ ]] || { echo "failure percent must be 0-100" >&2; exit 2; }
APP=$(az webapp list --resource-group "$RG" --query "[0].name" --output tsv)
az webapp config appsettings set --resource-group "$RG" --name "$APP" \
  --settings "Chaos__FailurePercent=$PCT" --query "[?name=='Chaos__FailurePercent']" --output table
