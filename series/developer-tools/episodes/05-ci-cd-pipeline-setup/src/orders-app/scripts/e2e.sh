#!/usr/bin/env bash
# End-to-end test of the real image against a real SQL Server, with episode 4's compose.yaml.
# Same script in GitHub Actions (job "e2e") and on a laptop with Docker:
#   scripts/e2e.sh
# 1. a throwaway SA password in .env (masked in the Actions log, never printed)
# 2. docker compose up --build --wait: SQL Server healthy, then the API built from the Dockerfile
# 3. the xUnit tests marked Category=SqlServer, against that SQL Server (all four must run, none skipped)
# 4. tools/smoke.py against the API container (expects SqlServer and this commit's version)
# 5. always: logs on failure, docker compose down -v
set -euo pipefail
cd "$(dirname "$0")/.."

DOCKER=${DOCKER:-docker}
DOTNET=${DOTNET:-dotnet}
PYTHON=${PYTHON:-python3}
export APP_VERSION=${APP_VERSION:-${GITHUB_SHA:-dev}}

if [[ -e .env ]]; then
  echo "e2e: .env already exists; refusing to overwrite it (move it away first)" >&2
  exit 2
fi

# SQL Server policy: 8+ characters from three of four sets. 32 random hex digits plus a fixed "-Aa1" suffix.
# (Not `tr </dev/urandom | head`: with pipefail, tr's SIGPIPE ends the script with exit 141.)
password="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')-Aa1"
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "::add-mask::${password}"            # before anything else can print it
fi
umask 077
printf 'MSSQL_SA_PASSWORD=%s\n' "$password" > .env

cleanup() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "e2e: failed (exit $rc), container logs follow" >&2
    "$DOCKER" compose logs --no-color --tail 200 >&2 || true
  fi
  "$DOCKER" compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f .env
  exit $rc
}
trap cleanup EXIT

echo "e2e: starting SQL Server and the API (version ${APP_VERSION})"
"$DOCKER" compose up --build --wait --wait-timeout 240

echo "e2e: integration tests against SQL Server"
ORDERS_SQLSERVER_TESTS="Server=127.0.0.1,1433;Database=master;User Id=sa;Password=${password};TrustServerCertificate=True" \
  "$DOTNET" test --filter "Category=SqlServer" --logger "trx;LogFileName=sqlserver.trx" \
    --results-directory TestResults

# A filter that matches nothing, or tests that skip, still exit 0: require four tests that actually ran.
"$PYTHON" tools/trx_check.py TestResults/sqlserver.trx --min-passed 4 --no-skipped

echo "e2e: smoke test against the API container"
"$PYTHON" tools/smoke.py http://127.0.0.1:8080 --database SqlServer --version "$APP_VERSION" --timeout 120 --interval 3
