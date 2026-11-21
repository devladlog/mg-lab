#!/usr/bin/env bash
# Walks through the episode against a running API: idempotent create, keyset paging,
# optimistic concurrency, and an invoice download through a user delegation SAS.
# Usage: infra/smoke.sh [base-url]     (default http://localhost:5199)
set -euo pipefail
BASE=${1:-http://localhost:5199}
RUN=${RUN_ID:-$(date +%s)}
CUSTOMER="alex-demo-$RUN"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
json() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {"d": d}))' "$1" "$2"; }
# post <idempotency-key> <body> -> prints the HTTP status, body in $TMP/body, headers in $TMP/headers
post() { curl -sS -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' -X POST "$BASE/orders" \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $1" -d "$2"; }
header() { grep -i "^$1:" "$TMP/headers" | head -1 | cut -d' ' -f2- | tr -d '\r'; }
expect() { [ "$2" = "$3" ] && echo "  ok   $1 -> $3" || { echo "  FAIL $1: expected $2, got $3" >&2; cat "$TMP/body" >&2; exit 1; }; }

ORDER='{"customerId":"'"$CUSTOMER"'","lines":[{"sku":"MON-270","quantity":2},{"sku":"DOC-100","quantity":1}]}'
OTHER='{"customerId":"'"$CUSTOMER"'","lines":[{"sku":"CBL-001","quantity":3}]}'

echo "== idempotent create"
expect "POST key $RUN-a"                  201 "$(post "$RUN-a" "$ORDER")"
ID=$(json "$TMP/body" 'd["id"]'); ETAG=$(header ETag)
echo "       order $ID, total $(json "$TMP/body" 'd["total"]') EUR, ETag $ETAG"
expect "same key, same body (replay)"     200 "$(post "$RUN-a" "$ORDER")"
expect "  Idempotent-Replay header"       true "$(header Idempotent-Replay)"
expect "  same order id"                  "$ID" "$(json "$TMP/body" 'd["id"]')"
expect "same key, different body"         409 "$(post "$RUN-a" "$OTHER")"

echo "== keyset paging (3 more orders, pages of 2)"
for k in b c d; do expect "POST key $RUN-$k" 201 "$(post "$RUN-$k" "$OTHER")"; done
curl -sS -o "$TMP/p1" "$BASE/customers/$CUSTOMER/orders?take=2"
NEXT=$(json "$TMP/p1" 'd["next"]')
echo "       page 1: $(json "$TMP/p1" '[o["id"] for o in d["items"]]')  next=$NEXT"
curl -sS -o "$TMP/p2" "$BASE/customers/$CUSTOMER/orders?take=2&after=$NEXT"
echo "       page 2: $(json "$TMP/p2" '[o["id"] for o in d["items"]]')  next=$(json "$TMP/p2" 'd["next"]')"
expect "page 2 ends the list"             None "$(json "$TMP/p2" 'd["next"]')"

echo "== optimistic concurrency"
STALE='"00000000000000000000000000000000"'
code=$(curl -sS -o "$TMP/body" -w '%{http_code}' -X POST "$BASE/orders/$ID/cancel" -H "If-Match: $STALE")
expect "cancel with a stale ETag"         412 "$code"
code=$(curl -sS -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' -X POST "$BASE/orders/$ID/cancel" -H "If-Match: $ETAG")
expect "cancel with the current ETag"     200 "$code"
code=$(curl -sS -o "$TMP/body" -w '%{http_code}' -X POST "$BASE/orders/$ID/cancel" -H "If-Match: $ETAG")
expect "replay the old ETag"              412 "$code"

echo "== invoice through a user delegation SAS"
code=$(curl -sS -o "$TMP/link" -w '%{http_code}' "$BASE/orders/$ID/invoice")
if [ "$code" = 503 ]; then echo "  skip invoice storage not configured (local run)"; exit 0; fi
expect "GET /orders/$ID/invoice"          200 "$code"
URL=$(json "$TMP/link" 'd["url"]')
echo "       expires $(json "$TMP/link" 'd["expiresOn"]')"
echo "       SAS fields: $(python3 -c 'import sys,urllib.parse as u; q=u.parse_qs(u.urlparse(sys.argv[1]).query); print(" ".join(f"{k}={q[k][0]}" for k in ("sp","sr","spr","skoid") if k in q))' "$URL" | sed -E 's/skoid=[0-9a-f-]+/skoid=<object id>/')"
expect "download with the SAS"            200 "$(curl -sS -o "$TMP/invoice" -w '%{http_code}' "$URL")"
echo "       invoice customer: $(json "$TMP/invoice" 'd["customerId"]')"
expect "same URL, permission changed to write" 403 "$(curl -sS -o /dev/null -w '%{http_code}' "${URL/sp=r/sp=rw}")"
echo "All checks passed."
