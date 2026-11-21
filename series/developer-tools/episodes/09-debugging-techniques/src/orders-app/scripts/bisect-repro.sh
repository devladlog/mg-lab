#!/usr/bin/env bash
# The check `git bisect run` calls at every step: does the month-end bug reproduce at this commit?
#   exit 0       the test passes   -> good commit
#   exit 1       the test fails    -> bad commit
#   exit 125     cannot be tested here (does not build, or the test does not exist yet) -> git bisect skips the commit
#
#   git bisect start HEAD <last-known-good>
#   git bisect run scripts/bisect-repro.sh
set -u
cd "$(dirname "$0")/.."

TEST='MonthEnd_orders_are_part_of_the_month'
project=tests/Contoso.Orders.Api.Tests/Contoso.Orders.Api.Tests.csproj

if ! dotnet build "$project" --nologo -v q >/dev/null 2>&1; then
    echo "bisect-repro: does not build, skip" >&2
    exit 125
fi

out=$(dotnet test "$project" --no-build --nologo --filter "FullyQualifiedName~$TEST" 2>&1)
status=$?
echo "$out" | tail -n 3

# "dotnet test --filter" with a filter that matches nothing is not an error: it prints a warning and exits 0.
# Without this check a commit from before the test existed would be reported as good.
if ! grep -qE 'Passed: +1|Failed: +[1-9]' <<<"$out"; then
    echo "bisect-repro: test $TEST did not run, skip" >&2
    exit 125
fi
[[ $status -eq 0 ]] && exit 0 || exit 1
