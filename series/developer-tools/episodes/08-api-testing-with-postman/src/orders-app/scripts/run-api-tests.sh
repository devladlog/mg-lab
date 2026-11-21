#!/usr/bin/env bash
# Run the Postman collection against the orders API, headless, the same way on a laptop and in CI.
#
#   scripts/run-api-tests.sh                              start the API from source (dotnet), test it, stop it
#   BASE_URL=http://localhost:8080 scripts/run-api-tests.sh --no-start
#                                                         test an API that is already running (a container, a deployment)
#   EXPECTED_VERSION=<sha> ...                            also require /healthz to report that version
#
# Two Newman runs, because the data-driven folder needs a data file and the rest must run once:
#   1. Health, Orders and Validation
#   2. Data-driven, one iteration per row of data/invalid-orders.json
# JUnit reports go to api-tests/results/; junit_gate.py fails the script when too few tests ran.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tests="$root/api-tests"
results="${RESULTS_DIR:-$tests/results}"
start=true
[[ "${1:-}" == "--no-start" ]] && start=false

PYTHON="${PYTHON:-python3}"
DOTNET="${DOTNET:-dotnet}"
NEWMAN="${NEWMAN:-$tests/node_modules/.bin/newman}"
[[ -x "$NEWMAN" ]] || { echo "Newman is not installed: run 'npm ci' in api-tests/" >&2; exit 2; }

api_pid=""
cleanup() {
  if [[ -n "$api_pid" ]]; then kill "$api_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; fi
  if [[ -n "${db_file:-}" ]]; then rm -f "$db_file" "$db_file-shm" "$db_file-wal"; fi
  return 0        # a failing last command here would change the script's exit status
}
trap cleanup EXIT

if $start; then
  port="${API_PORT:-$("$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')}"
  BASE_URL="http://127.0.0.1:${port}"
  db_file="$(mktemp -u "${TMPDIR:-/tmp}/orders-apitests-XXXXXX.db")"
  echo "Starting the API on $BASE_URL"
  # Production, like the container: Development would turn error responses into HTML/debug pages.
  ASPNETCORE_ENVIRONMENT=Production DOTNET_ENVIRONMENT=Production \
  Database__Provider=Sqlite ConnectionStrings__Orders="Data Source=$db_file;Pooling=False" \
  App__Version="${EXPECTED_VERSION:-dev}" \
    "$DOTNET" run --project "$root/src/Contoso.Orders.Api" --no-launch-profile --urls "$BASE_URL" \
      >"${TMPDIR:-/tmp}/orders-apitests-api.log" 2>&1 &
  api_pid=$!
else
  : "${BASE_URL:?set BASE_URL when using --no-start}"
fi

echo "Waiting for $BASE_URL/healthz"
for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/healthz" >/dev/null 2>&1; then ready=true; break; fi
  if [[ -n "$api_pid" ]] && ! kill -0 "$api_pid" 2>/dev/null; then
    echo "The API exited early:" >&2; cat "${TMPDIR:-/tmp}/orders-apitests-api.log" >&2; exit 3
  fi
  sleep 1
done
[[ "${ready:-false}" == "true" ]] || { echo "The API did not become healthy in 60 s" >&2; exit 3; }

mkdir -p "$results"
cd "$tests"
common=(-e environments/local.postman_environment.json --env-var "baseUrl=$BASE_URL"
        --env-var "expectedVersion=${EXPECTED_VERSION:-}" --reporters cli,junit)

status=0
"$NEWMAN" run orders-api.postman_collection.json "${common[@]}" \
  --folder Health --folder Orders --folder Validation \
  --reporter-junit-export "$results/junit-main.xml" || status=1
"$NEWMAN" run orders-api.postman_collection.json "${common[@]}" \
  --folder Data-driven -d data/invalid-orders.json \
  --reporter-junit-export "$results/junit-data.xml" || status=1

# Newman exits 0 for a collection without tests. Count what ran.
"$PYTHON" tools/junit_gate.py "$results/junit-main.xml" --min-tests 31 || status=1
"$PYTHON" tools/junit_gate.py "$results/junit-data.xml" --min-tests 24 || status=1
exit $status
