#!/usr/bin/env bash
# Deletes the waste demo and the empty what-if group. The budget is free and stays unless --with-budget.
# Usage: infra/teardown.sh <waste-resource-group> [whatif-resource-group] [--with-budget]
set -euo pipefail
WASTE=${1:?usage: teardown.sh <waste-resource-group> [whatif-resource-group] [--with-budget]}
WHATIF=${2:-}
az group delete --name "$WASTE" --yes --no-wait
if [[ -n "$WHATIF" && "$WHATIF" != "--with-budget" ]]; then az group delete --name "$WHATIF" --yes --no-wait; fi
if [[ " $* " == *" --with-budget "* ]]; then
  SUB=$(az account show --query id --output tsv)
  az rest --method delete \
    --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/budget-contoso-lab?api-version=2023-11-01"
fi
echo "Deletion started. Check: az group exists --name $WASTE"
