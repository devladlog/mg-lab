#!/usr/bin/env bash
# 1. Builds the legacy project with the clean-code gates switched on and checks the diagnostics the video shows.
# 2. Builds the clean project with the same gates (must pass).
# 3. Runs the golden-master comparison with the kept rounding and with the "obvious improvement".
# Exit code 0 = everything behaved as described in the video.
set -uo pipefail
cd "$(dirname "$0")/.."
root="$(pwd)/"
status=0
check() { if grep -qF -- "$2" <<< "$1"; then echo "ok   $3"; else echo "FAIL $3"; status=1; fi; }

echo "### legacy code + gates: dotnet build src/Contoso.Requests.Legacy -p:EnforceCleanCode=true"
out=$(dotnet build src/Contoso.Requests.Legacy -m:1 --no-incremental -v q -p:EnforceCleanCode=true 2>&1 \
      | sed "s|$root||g; s| \[src[^]]*\]||; s| (https[^)]*)||")
echo "$out" | grep -E " error " | sort -u
echo "$(echo "$out" | grep -E " error " | sort -u | wc -l) distinct errors"
check "$out" "error CA1502: 'Process' has a cyclomatic complexity of '19'" "CA1502: complexity 19, gate is 10"
check "$out" "error CA1031" "CA1031: catch (Exception) swallows everything"
check "$out" "error IDE0011" "IDE0011: if/else without braces"
check "$out" "error IDE0059" "IDE0059: value assigned and never used"

echo
echo "### clean code + the same gates"
clean=$(dotnet build src/Contoso.Requests.Clean -m:1 --no-incremental -v q 2>&1)
check "$clean" "0 Error(s)" "clean project builds with the gates on"

dotnet build src/Contoso.Requests.Cli -m:1 -v q > /dev/null
echo
echo "### golden master: dotnet run -- compare samples/requests.csv"
cmp=$(dotnet run --no-build --project src/Contoso.Requests.Cli -- compare samples/requests.csv); echo "$cmp"
check "$cmp" "38 identical, 2 different" "only line 7 (the 50,000 boundary) differs, on purpose"

echo
echo "### the 'obvious improvement': --rounding AwayFromZero"
away=$(dotnet run --no-build --project src/Contoso.Requests.Cli -- compare samples/requests.csv --rounding AwayFromZero)
echo "$away" | grep -E "DIFF|identical"
check "$away" "36 identical, 4 different" "line 9 (12,500.5) changes too: the master catches it"
exit $status
