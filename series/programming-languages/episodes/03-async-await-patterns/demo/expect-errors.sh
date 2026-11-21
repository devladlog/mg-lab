#!/usr/bin/env bash
# Builds demo/Analyzers (wrong on purpose) and checks that each diagnostic the video mentions is reported.
# Then runs the CLI deadlock demo (no API needed). Exit code 0 = everything behaved as described.
set -uo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)/"

out=$(dotnet build demo/Analyzers -m:1 --no-incremental -v q 2>&1 | sed "s|$root||g")
echo "$out" | grep -E "error (CS|CA)[0-9]+" | sort -u
status=0
for id in CS4014 CA2016 CA1849; do
  if echo "$out" | grep -q "error $id"; then echo "ok   $id is a build error"; else echo "FAIL $id not reported"; status=1; fi
done

echo
echo "Same project with TreatWarningsAsErrors=false:"
soft=$(dotnet build demo/Analyzers -m:1 --no-incremental -p:TreatWarningsAsErrors=false 2>&1)
if echo "$soft" | grep -q "Build succeeded"; then echo "ok   build succeeds, the three are only warnings"; else echo "FAIL expected a successful build"; status=1; fi

echo
dotnet run --project src/Contoso.Approvals.Cli -- deadlock
exit $status
