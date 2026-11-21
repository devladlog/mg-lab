#!/usr/bin/env bash
# Everything the CI stage checks, runnable on a laptop too. No Azure sign-in needed.
#   ci.sh <output-dir>          results in <output-dir>/test-results, probe package in <output-dir>/probe
# Needs: python3 + pytest + pyyaml, bicep, dotnet 10, zip; pwsh + PSRule.Rules.Azure unless SKIP_PSRULE=1.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1   # no __pycache__ in the source tree

OUT=$(mkdir -p "${1:?usage: ci.sh <output-dir>}" && cd "$1" && pwd)
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EP3=$(cd "$HERE/../.." && pwd)
EP2=$(cd "$EP3/../02-cloud-architecture" && pwd)
RESULTS="$OUT/test-results"
mkdir -p "$RESULTS" "$OUT/probe"

step() { echo; echo "== $*"; }

step "1. pipeline contract (templates, stages, service connections, approvals order)"
PYTHONPATH="$EP3/src" python3 -m pipeline_contract "$EP3/pipelines/azure-pipelines.yml" --approval-env contoso-prod

step "2. pytest: pipeline contract + what-if gate + scripts (episode 3)"
python3 -m pytest "$EP3/tests" -q -p no:cacheprovider --junitxml="$RESULTS/pipeline-tests.xml"

step "3. pytest: architecture guardrails on the compiled Bicep (episode 2)"
python3 -m pytest "$EP2/tests/guardrails" -q -p no:cacheprovider --junitxml="$RESULTS/guardrails.xml"

step "4. Bicep lint (rules in bicepconfig.json are set to error)"
(cd "$EP2/infra" && bicep lint main.bicep && bicep lint governance.bicep)

step "5. xUnit: readiness probe"
# --artifacts-path keeps bin/ and obj/ out of the source tree (and out of the episode 2 folder)
dotnet test "$EP2/tests/ReadinessProbe.Tests" -m:1 --nologo --artifacts-path "$OUT/artifacts" \
  --logger "trx;LogFileName=probe.trx" --results-directory "$RESULTS"

if [[ "${SKIP_PSRULE:-0}" == "1" ]]; then
  step "6. PSRule for Azure: SKIPPED (SKIP_PSRULE=1)"
else
  step "6. PSRule for Azure (Well-Architected rules, both environments)"
  pwsh -NoProfile -File "$EP2/infra/Invoke-Guardrails.ps1"
fi

step "7. package the probe"
dotnet publish "$EP2/src/ReadinessProbe/ReadinessProbe.csproj" -c Release -m:1 --nologo \
  --artifacts-path "$OUT/artifacts" -o "$OUT/publish"
rm -f "$OUT/probe/probe.zip"
(cd "$OUT/publish" && zip -qr "$OUT/probe/probe.zip" .)
ls -l "$OUT/probe/probe.zip"
