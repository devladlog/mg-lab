#!/usr/bin/env bash
# Profile the running API while a repeatable load hits the report.
# Usage: scripts/profile.sh <base-url> <pid> [seconds=15] [output-folder=profile]
#   1. tools/load.py runs for the whole window (cache emptied before every request)
#   2. dotnet-counters collect: runtime and ASP.NET Core metrics, one sample per second, as JSON
#   3. dotnet-trace collect: sampled thread time, converted to a Speedscope file
#   4. the three summaries: the load's p50/p95, tools/counters_summary.py, tools/speedscope_top.py
# Measure a Release build (Learn, Debug ASP.NET apps: for performance measurements specify a Release build).
set -euo pipefail
cd "$(dirname "$0")/.."

base="${1:?usage: profile.sh <base-url> <pid> [seconds] [output-folder]}"
pid="${2:?usage: profile.sh <base-url> <pid> [seconds] [output-folder]}"
seconds="${3:-15}"
out="${4:-profile}"
py="$(command -v python3 || command -v python)"
span="$(printf '00:00:%02d:%02d' $((seconds / 60)) $((seconds % 60)))"          # dd:hh:mm:ss

dotnet tool restore >/dev/null                                                  # versions pinned in .config/dotnet-tools.json
mkdir -p "$out"

"$py" tools/load.py "$base" --seconds $((seconds + 8)) --workers 2 > "$out/load.txt" &
load=$!
sleep 2                                                                         # let the load warm the process up first
dotnet tool run dotnet-counters collect -p "$pid" --format json -o "$out/counters" \
    --counters System.Runtime,Microsoft.AspNetCore.Hosting --duration "$span" > "$out/counters.log" 2>&1 &
counters=$!
dotnet tool run dotnet-trace collect -p "$pid" --profile dotnet-sampled-thread-time --format Speedscope \
    -o "$out/trace.nettrace" --duration "$span" > "$out/trace.log" 2>&1
wait "$counters"
wait "$load" || true                                                            # load.py exits 1 on request errors: shown below

echo "== load:      $(cat "$out/load.txt")"
echo "== counters:"
"$py" tools/counters_summary.py "$out/counters.json"
echo "== where the threads were busy (trace):"
"$py" tools/speedscope_top.py "$out/trace.speedscope.json" --top 6 --match Contoso.Orders.Api!Contoso.Orders.Api.Reports.MonthlyRevenueAsync
echo "files: $out/ (open trace.speedscope.json in https://www.speedscope.app, it is read in the browser)"
