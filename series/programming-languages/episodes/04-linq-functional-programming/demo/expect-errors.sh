#!/usr/bin/env bash
# Builds demo/Analyzers (wrong on purpose) and checks that CA1851 is reported, then runs the deferred demo.
# Exit code 0 = everything behaved as described in the video.
set -uo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)/"

out=$(dotnet build demo/Analyzers -m:1 --no-incremental -v q 2>&1 | sed "s|$root||g")
echo "$out" | grep -E "error CA1851" | sort -u
status=0
if echo "$out" | grep -q "error CA1851"; then echo "ok   CA1851 is a build error (enabled in .editorconfig)"; else echo "FAIL CA1851 not reported"; status=1; fi

echo
echo "Same project with TreatWarningsAsErrors=false:"
soft=$(dotnet build demo/Analyzers -m:1 --no-incremental -p:TreatWarningsAsErrors=false 2>&1)
if echo "$soft" | grep -q "warning CA1851"; then echo "ok   still a warning with TreatWarningsAsErrors=false"; else echo "FAIL expected a CA1851 warning"; status=1; fi

echo
dotnet run --project src/Contoso.Portfolio.Cli -- deferred
exit $status
