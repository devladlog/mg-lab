#!/usr/bin/env bash
# Shows the guardrails at work: both requests should fail with RequestDisallowedByPolicy.
# Usage: infra/try-policy.sh <resource-group> <a region NOT in allowedLocations>
set -uo pipefail
RG=${1:?usage: try-policy.sh <resource-group> <other-region>}
OTHER=${2:?give a region outside the allowed list, e.g. westeurope}

echo "--- 1. right tags, wrong region"
az network nsg create -g "$RG" -n nsg-policy-test-region -l "$OTHER" --tags workload=contoso --output none 2>&1 | tail -3

echo "--- 2. right region, no workload tag"
az network nsg create -g "$RG" -n nsg-policy-test-tag --output none 2>&1 | tail -3
