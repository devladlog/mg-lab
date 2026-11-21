#!/usr/bin/env bash
# Mixed traffic for the demo: valid orders (web + partner), invalid ones (400), unknown SKUs (422),
# unknown ids (404). Prints a tally of status codes. Usage: infra/load.sh <base-url> [rounds]
set -euo pipefail
BASE=${1:?usage: load.sh <base-url> [rounds]}
ROUNDS=${2:-50}
declare -A TALLY=()

post() { curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/orders" -H 'content-type: application/json' -d "$1"; }
count() { TALLY[$1]=$(( ${TALLY[$1]:-0} + 1 )); }

for i in $(seq 1 "$ROUNDS"); do
  count "$(post '{"customerId":"C-'"$i"'","channel":"web","lines":[{"sku":"MON-270","quantity":2},{"sku":"KEY-010","quantity":2}]}')"
  count "$(post '{"customerId":"C-'"$i"'","channel":"partner","lines":[{"sku":"DOC-100","quantity":1},{"sku":"CBL-001","quantity":3}]}')"
  if (( i % 5 == 0 )); then count "$(post '{"channel":"fax","lines":[]}')"; fi
  if (( i % 7 == 0 )); then count "$(post '{"customerId":"C-'"$i"'","channel":"web","lines":[{"sku":"ZZZ-999","quantity":1}]}')"; fi
  if (( i % 10 == 0 )); then count "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/orders/does-not-exist")"; fi
done

for code in $(printf '%s\n' "${!TALLY[@]}" | sort); do echo "HTTP $code: ${TALLY[$code]}"; done
