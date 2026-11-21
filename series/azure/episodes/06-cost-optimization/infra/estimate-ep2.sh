#!/usr/bin/env bash
# What-if (creates nothing) for episode 2's lab and prod profiles against an empty resource group,
# then price both with costwatch. Needs: az (signed in), python3.
# Usage: infra/estimate-ep2.sh <empty-resource-group> [region] [monthly-budget]
set -euo pipefail
RG=${1:?usage: estimate-ep2.sh <empty-resource-group> [region] [monthly-budget]}
REGION=${2:-swedencentral}
BUDGET=${3:-25}
HERE=$(cd "$(dirname "$0")" && pwd)
EP2=$(cd "$HERE/../../02-cloud-architecture/infra" && pwd)
OUT="$HOME/.contoso-cost"            # what-if JSON + price cache, kept outside the repo
mkdir -p "$OUT"

az group create --name "$RG" --location "$REGION" --tags workload=contoso environment=lab --output none
status=0
for ENV in lab prod; do
  echo "== what-if: episode 2, $ENV profile"
  az deployment group what-if --resource-group "$RG" --parameters "$EP2/env/$ENV.bicepparam" \
    --no-pretty-print --output json > "$OUT/whatif-$ENV.json"
  echo "== estimate ($ENV), budget $BUDGET"
  PYTHONPATH="$HERE/../src" python3 -m costwatch --cache "$OUT/prices.json" \
    estimate "$OUT/whatif-$ENV.json" --budget "$BUDGET" || status=$?
done
exit $status   # 1 = at least one profile is over budget (prod, on purpose)
