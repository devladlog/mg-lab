#!/usr/bin/env bash
# The same service without the SDK: one language detection call with a bearer token from the Azure CLI, and the same call
# with a made-up key header, to show what "key access disabled" looks like on the wire.
# Usage: infra/rest-check.sh
set -euo pipefail
ENDPOINT=${LANGUAGE_ENDPOINT:-$(cat "$HOME/.contoso-ai/endpoint")}
ENDPOINT=${ENDPOINT%/}
URL="$ENDPOINT/language/:analyze-text?api-version=2023-04-01"
BODY='{"kind":"LanguageDetection","analysisInput":{"documents":[{"id":"1","text":"Boa tarde, a minha encomenda chegou partida."}]}}'

echo "== with an Entra ID token (az account get-access-token --resource https://cognitiveservices.azure.com)"
TOKEN=$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)
curl -sS -o /dev/stdout -w '\nHTTP %{http_code}\n' -X POST "$URL" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$BODY"

echo "== with a key header (key access is disabled, so any key must be refused)"
curl -sS -o /dev/stdout -w '\nHTTP %{http_code}\n' -X POST "$URL" -H "Ocp-Apim-Subscription-Key: 00000000000000000000000000000000" -H "Content-Type: application/json" -d "$BODY"
