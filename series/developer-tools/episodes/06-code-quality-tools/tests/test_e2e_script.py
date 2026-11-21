"""scripts/e2e.sh with fake `docker`, `dotnet` and `python3` on PATH (no Docker on the build machine).
The real run happens in the e2e job and on the recording laptop; here we prove the script's own logic:
order of steps, the password never printed, .env private and removed, cleanup on failure."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import copy_app

FAKE = r"""#!/usr/bin/env bash
# records argv and, for `compose up`, the mode of .env at that moment
echo "$(basename "$0") $*" >> "$CALLS"
if [[ "$(basename "$0")" == docker && "$1 $2" == "compose up" ]]; then
  stat -c '%a' .env >> "$CALLS"; cat .env > "$SEEN_ENV"
fi
if [[ "$(basename "$0")" == dotnet && -n "${FAIL_TESTS:-}" ]]; then echo "1 test failed" >&2; exit 1; fi
if [[ "$(basename "$0")" == dotnet ]]; then echo "ORDERS_SQLSERVER_TESTS=$ORDERS_SQLSERVER_TESTS" >> "$CALLS"; fi
exit 0
"""


@pytest.fixture
def app(tmp_path):
    root = copy_app(tmp_path)
    bin_ = tmp_path / "fakebin"
    bin_.mkdir()
    for name in ("docker", "dotnet", "python3"):
        (bin_ / name).write_text(FAKE)
        (bin_ / name).chmod(0o755)
    env = dict(os.environ, CALLS=str(tmp_path / "calls.log"), SEEN_ENV=str(tmp_path / "seen.env"),
               DOCKER=str(bin_ / "docker"), DOTNET=str(bin_ / "dotnet"), PYTHON=str(bin_ / "python3"),
               APP_VERSION="3f2c1e0")
    env.pop("GITHUB_ACTIONS", None)
    return root, env, tmp_path


def e2e(root: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "scripts/e2e.sh"], cwd=root, env=env, capture_output=True, text=True, timeout=60)


def calls(tmp: Path) -> list[str]:
    return (tmp / "calls.log").read_text().splitlines()


def password(tmp: Path) -> str:
    return (tmp / "seen.env").read_text().strip().split("=", 1)[1]


def test_happy_path_runs_compose_tests_gate_smoke_then_cleans_up(app):
    root, env, tmp = app
    r = e2e(root, env)
    assert r.returncode == 0, r.stderr
    c = calls(tmp)
    assert c[0] == "docker compose up --build --wait --wait-timeout 240"
    assert c[1] == "600"                                                   # .env readable by us only
    assert c[2].startswith("dotnet test --filter Category=SqlServer")
    assert c[3].startswith("ORDERS_SQLSERVER_TESTS=Server=127.0.0.1,1433;") and "TrustServerCertificate=True" in c[3]
    assert c[4] == "python3 tools/trx_check.py TestResults/sqlserver.trx --min-passed 4 --no-skipped"
    assert c[5] == "python3 tools/smoke.py http://127.0.0.1:8080 --database SqlServer --version 3f2c1e0 --timeout 120 --interval 3"
    assert c[6] == "docker compose down -v --remove-orphans"
    assert not (root / ".env").exists()


def test_password_meets_the_sql_server_policy_and_is_never_printed(app):
    root, env, tmp = app
    r = e2e(root, env)
    pw = password(tmp)
    assert len(pw) >= 8 and sum(any(f(ch) for ch in pw) for f in (str.isupper, str.islower, str.isdigit)) == 3
    assert ";" not in pw and '"' not in pw                                 # safe inside a connection string
    assert pw not in r.stdout + r.stderr


def test_in_github_actions_the_password_is_masked_before_anything_else(app):
    root, env, tmp = app
    r = e2e(root, dict(env, GITHUB_ACTIONS="true"))
    first = r.stdout.splitlines()[0]
    assert first == f"::add-mask::{password(tmp)}"


def test_each_run_gets_a_new_password(app):
    root, env, tmp = app
    e2e(root, env)
    one = password(tmp)
    e2e(root, env)
    assert password(tmp) != one


def test_failing_tests_dump_logs_and_still_tear_down(app):
    root, env, tmp = app
    r = e2e(root, dict(env, FAIL_TESTS="1"))
    assert r.returncode == 1
    c = calls(tmp)
    assert "docker compose logs --no-color --tail 200" in c
    assert c[-1] == "docker compose down -v --remove-orphans"
    assert not any("smoke.py" in x for x in c)
    assert not (root / ".env").exists()


def test_refuses_to_overwrite_an_existing_env_file(app):
    root, env, tmp = app
    (root / ".env").write_text("MSSQL_SA_PASSWORD=my-own-dev-password\n")
    r = e2e(root, env)
    assert r.returncode == 2 and "refusing to overwrite" in r.stderr
    assert (root / ".env").read_text() == "MSSQL_SA_PASSWORD=my-own-dev-password\n"
    assert not (tmp / "calls.log").exists()


def test_script_is_executable_and_lf():
    from conftest import APP
    script = APP / "scripts" / "e2e.sh"
    assert script.stat().st_mode & stat.S_IXUSR
    assert b"\r\n" not in script.read_bytes()
