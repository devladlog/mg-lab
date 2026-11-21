#!/usr/bin/env bash
# A process is alive but requests never finish. Usage: scripts/triage-hang.sh <pid> [output-folder]
#   1. dotnet-stack: where is every thread right now? (fast, no file, the process keeps running)
#   2. dotnet-dump:  a dump with heap, then syncblk (who owns which lock) and clrstack -all (with file and line)
# The dump is a copy of the process memory: customer names, tokens, connection strings. Keep it off shared drives, delete it afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."

pid="${1:?usage: triage-hang.sh <pid> [output-folder]}"
out="${2:-triage}"
mkdir -p "$out"
dotnet tool restore >/dev/null            # versions pinned in dotnet-tools.json

echo "== threads (dotnet-stack report)"
dotnet tool run dotnet-stack report -p "$pid" > "$out/stacks.txt"
grep -c '^Thread' "$out/stacks.txt" | sed 's/^/threads: /'
grep -B3 -E 'Contoso\.Orders\.Api!' "$out/stacks.txt" | grep -E 'Thread \(|Monitor\.Enter|Contoso\.Orders\.Api!Contoso' || true

echo "== dump with heap (dotnet-dump collect)"
dotnet tool run dotnet-dump collect -p "$pid" --type Heap -o "$out/hang.dmp" | tail -n 1

echo "== lock owners (syncblk) and the stacks that wait (clrstack -all)"
dotnet tool run dotnet-dump analyze "$out/hang.dmp" -c syncblk -c "clrstack -all" -c exit > "$out/analysis.txt"
sed -n '/^Index/,/^Total/p' "$out/analysis.txt"
grep -E 'ReportCache\.[A-Za-z]+\(\) \[' "$out/analysis.txt" || true
echo "files: $out/stacks.txt $out/analysis.txt $out/hang.dmp (delete hang.dmp when done)"
