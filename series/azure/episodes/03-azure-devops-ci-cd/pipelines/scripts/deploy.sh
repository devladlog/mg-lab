#!/usr/bin/env bash
# what-if -> gate -> deploy Bicep -> publish the probe package -> wait for /healthz.
# Runs inside AzureCLI@2 (already signed in through the workload identity federation service connection),
# or on a laptop after `az login`. Needs: az, python3, curl.
#
#   deploy.sh --resource-group RG --parameters env/lab.bicepparam --policy gate-policy.json
#             [--package probe.zip] [--accept-protected true|false] [--summary out.md]
#             [--save-whatif out.json] [--plan-only] [--azure-devops]
#
# Exit codes: 0 deployed (or plan passed), 1 blocked by the gate, 2 usage error / what-if unusable, other = az/curl.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SRC=$(cd "$HERE/../../src" && pwd)

usage() { sed -n '6,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }

RG="" PARAMS="" POLICY="" PKG="" ACCEPT="false" SUMMARY="" SAVE_WHATIF="" PLAN_ONLY=0 ADO=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group) RG=${2:?}; shift 2 ;;
    --parameters)     PARAMS=${2:?}; shift 2 ;;
    --policy)         POLICY=${2:?}; shift 2 ;;
    --package)        PKG=${2:?}; shift 2 ;;
    --accept-protected) ACCEPT=${2:?}; shift 2 ;;
    --summary)        SUMMARY=${2:?}; shift 2 ;;
    --save-whatif)    SAVE_WHATIF=${2:?}; shift 2 ;;
    --plan-only)      PLAN_ONLY=1; shift ;;
    --azure-devops)   ADO=1; shift ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done
[[ -n "$RG" && -n "$PARAMS" && -n "$POLICY" ]] || usage
[[ $PLAN_ONLY -eq 1 || -n "$PKG" ]] || { echo "--package is required unless --plan-only" >&2; usage; }
[[ -f "$PARAMS" ]] || { echo "parameters file not found: $PARAMS" >&2; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "== 1. what-if: $RG <- $PARAMS"
# A .bicepparam file names its template ("using '../main.bicep'"), so no --template-file here.
az deployment group what-if --resource-group "$RG" --parameters "$PARAMS" \
  --no-pretty-print --output json > "$WORK/whatif.json"
if [[ -n "$SAVE_WHATIF" ]]; then mkdir -p "$(dirname "$SAVE_WHATIF")"; cp "$WORK/whatif.json" "$SAVE_WHATIF"; fi

echo "== 2. gate"
gate=(--whatif "$WORK/whatif.json" --policy "$POLICY" --title "What-if gate: $RG")
[[ -n "$SUMMARY" ]] && { mkdir -p "$(dirname "$SUMMARY")"; gate+=(--summary "$SUMMARY"); }
[[ "${ACCEPT,,}" == "true" ]] && gate+=(--accept-protected)
[[ $ADO -eq 1 ]] && gate+=(--azure-devops)
rc=0
PYTHONPATH="$SRC" python3 -m whatif_gate "${gate[@]}" || rc=$?
if [[ $rc -ne 0 ]]; then
  echo "gate said no (exit $rc): nothing was deployed" >&2
  exit "$rc"
fi
if [[ $PLAN_ONLY -eq 1 ]]; then
  echo "plan only: stopping before deployment"
  exit 0
fi

NAME="workload-${BUILD_BUILDID:-local-$(date -u +%Y%m%d%H%M%S)}"
echo "== 3. deploy ($NAME)"
APP=$(az deployment group create --resource-group "$RG" --name "$NAME" --parameters "$PARAMS" \
  --query properties.outputs.appName.value --output tsv)
HEALTH=$(az deployment group show --resource-group "$RG" --name "$NAME" \
  --query properties.outputs.healthUrl.value --output tsv)

echo "== 4. publish probe package to $APP"
az webapp deploy --resource-group "$RG" --name "$APP" --src-path "$PKG" --type zip

echo "== 5. health: $HEALTH"
# Private endpoints, role assignments and VNet integration can take a few minutes after a first deployment.
curl --fail --silent --show-error --retry 10 --retry-delay 15 --retry-all-errors "$HEALTH"
echo
