#!/usr/bin/env bash
# Subscription-scope budget for the lab workloads (filtered by the workload tag).
# Usage: BUDGET_EMAIL=you@example.com infra/deploy-budget.sh [region-for-deployment-metadata]
set -euo pipefail
: "${BUDGET_EMAIL:?set BUDGET_EMAIL to the address that should receive budget alerts}"
REGION=${1:-swedencentral}
HERE=$(cd "$(dirname "$0")" && pwd)
az deployment sub what-if --location "$REGION" --parameters "$HERE/budget.bicepparam"
az deployment sub create --location "$REGION" --name budget-contoso-lab \
  --parameters "$HERE/budget.bicepparam" --query properties.outputs.budgetId.value --output tsv
