#!/usr/bin/env bash
# Runs the triage app against the deployed resource with the identity of the signed-in Azure CLI user.
# Usage: infra/run.sh [extra SupportTriage arguments]      e.g.  infra/run.sh --dry-run
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
export LANGUAGE_ENDPOINT=${LANGUAGE_ENDPOINT:-$(cat "$HOME/.contoso-ai/endpoint")}
exec dotnet run --project "$HERE/../src/SupportTriage" -c Release -- "$@"
