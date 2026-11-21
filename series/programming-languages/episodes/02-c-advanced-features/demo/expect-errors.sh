#!/usr/bin/env bash
# Builds the projects that are wrong on purpose and checks they fail (or behave) exactly as the video says.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
check() { if grep -q -- "$2" <<<"$1"; then echo "  ok   $3"; else echo "  FAIL $3 (expected: $2)"; fail=1; fi; }

echo "== dotnet build demo/Gotchas (expected to fail)"
out=$(dotnet build demo/Gotchas -m:1 -nologo -v q 2>&1 | sed "s#$(pwd)/##g" | sort -u)
grep -E "error" <<<"$out" | grep -v "Error(s)" | cut -c1-200
check "$out" "NotExhaustive.cs(9,61): error CS8509" "CS8509 switch over a 'closed' record hierarchy is not exhaustive"
check "$out" "FieldKeyword.cs(12,16): error CS9258" "CS9258 'field' now means the backing field, not the member"
check "$out" "FieldKeyword.cs(10,19): error CS9264" "CS9264 the new backing field is never initialised"
if grep -q "PrimaryConstructor.cs" <<<"$out"; then echo "  FAIL PrimaryConstructor.cs should compile cleanly"; fail=1
else echo "  ok   reassigning a primary constructor parameter compiles without a warning"; fi
if grep -q "LinqClash.cs" <<<"$out"; then echo "  FAIL LinqClash.cs should compile cleanly"; fail=1
else echo "  ok   LinqClash.cs compiles without a warning"; fi

echo "== dotnet run --project demo/CSharp13"
dotnet build demo/CSharp13 -m:1 -nologo -v q >/dev/null 2>&1 || echo "  (build of demo/CSharp13 failed)"
run=$(dotnet run --project demo/CSharp13 --no-build 2>&1)
echo "  $run"
check "$run" "= 2" "C# 13 binds values.Average() to LINQ (C# 14 picks the span extension: see the unit test)"

exit $fail
