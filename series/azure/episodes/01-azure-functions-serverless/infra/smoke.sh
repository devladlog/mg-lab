#!/usr/bin/env bash
# Sends one valid, one invalid and one "poison" order.
# Local:  infra/smoke.sh http://localhost:7071
# Azure:  infra/smoke.sh https://<app>.azurewebsites.net "$(az functionapp function keys list -g <rg> -n <app> --function-name SubmitOrder --query default -o tsv)"
set -euo pipefail
BASE=${1:?usage: smoke.sh <base-url> [function-key]}
KEY=${2:-}
URL="$BASE/api/orders"
HDR=(-H "Content-Type: application/json")
[[ -n "$KEY" ]] && HDR+=(-H "x-functions-key: $KEY")

post() {
  echo "--- $1"
  curl -sS -o /dev/stdout -w "\nHTTP %{http_code}\n" -X POST "$URL" "${HDR[@]}" -d "$2"
}

post "valid order (expect 202)" \
  '{"customerId":"C-1001","lines":[{"sku":"MON-270","quantity":2},{"sku":"KEY-010","quantity":2}]}'
post "invalid order (expect 400)" \
  '{"customerId":"","lines":[{"sku":"monitor","quantity":0}]}'
post "well-formed, unknown SKU (expect 202, then 5 attempts and orders-poison)" \
  '{"customerId":"C-1002","lines":[{"sku":"ZZZ-999","quantity":1}]}'
