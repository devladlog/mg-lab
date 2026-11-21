#!/usr/bin/env bash
# Runs the four CLI modes shown in the video and checks each one behaved as described.
# Exit code 0 = everything behaved as the script says.
set -uo pipefail
cd "$(dirname "$0")/.."
cli=(dotnet run --no-build --project src/Contoso.Approvals.Patterns.Cli --)
dotnet build src/Contoso.Approvals.Patterns.Cli -m:1 -v q > /dev/null || exit 1
status=0
check() { if grep -qF -- "$2" <<< "$1"; then echo "ok   $3"; else echo "FAIL $3"; status=1; fi; }

echo "### 1. normal run"
out=$("${cli[@]}"); echo "$out"
check "$out" "audit trail (scoped): 4 entries  [ok]" "each batch has its own audit trail"
check "$out" "13 lookups, 10 file reads, 3 from cache" "decorators: cache served 3 of 13 lookups"

echo; echo "### 2. impossible policy"
out=$("${cli[@]}" --Policy:BoardThreshold=10000 2>&1); code=$?; echo "$out" | grep -vE '^\s+at |End of stack trace'
check "$out" "Startup failed in Production: OptionsValidationException" "ValidateOnStart stopped the app (exit $code)"

echo; echo "### 3. captive dependency, Production (default environment)"
out=$("${cli[@]}" --Demo:CaptiveAudit=true); echo "$out" | grep -E "environment|audit trail"
check "$out" "0 entries  [MISSING, expected 4]" "no error, but the audit trail is empty"

echo; echo "### 4. captive dependency, Development"
out=$("${cli[@]}" --Demo:CaptiveAudit=true --environment Development 2>&1); echo "$out"
check "$out" "Cannot consume scoped service" "Development validation refuses to build the host"
exit $status
