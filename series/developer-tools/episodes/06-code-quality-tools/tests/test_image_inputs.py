"""What episode 5 changed in episode 4's Dockerfile and compose.yaml, checked with episode 4's own linter."""
from __future__ import annotations

import re
import subprocess
import sys

import yaml

from conftest import APP

DOCKERFILE = (APP / "Dockerfile").read_text()


def lint(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "tools/container_lint.py", *args], cwd=APP, capture_output=True, text=True)


def test_container_lint_is_clean():
    r = lint()
    assert r.returncode == 0 and "0 error(s), 0 warning(s)" in r.stdout


def test_build_context_carries_the_lock_file_and_the_props():
    files = lint("context", ".").stdout.split()
    assert {"Directory.Build.props", "src/Contoso.Orders.Api/packages.lock.json"} <= set(files)
    assert ".env" not in files and not any(f.startswith("tests/") for f in files)


def test_dockerfile_restores_locked_before_copying_the_source():
    restore = DOCKERFILE.index("dotnet restore")
    assert "--locked-mode" in DOCKERFILE[restore:DOCKERFILE.index("\n", restore)]
    assert DOCKERFILE.index("packages.lock.json") < restore < DOCKERFILE.index("COPY src/ src/")
    assert DOCKERFILE.index("Directory.Build.props") < restore      # RestorePackagesWithLockFile lives there


def test_the_commit_reaches_healthz_through_arg_and_env():
    final = DOCKERFILE[DOCKERFILE.rindex("FROM "):]                # ARG must be declared in the final stage
    assert "ARG APP_VERSION=dev" in final
    assert re.search(r"App__Version=\$APP_VERSION", final)
    compose = yaml.safe_load((APP / "compose.yaml").read_text())
    assert compose["services"]["api"]["build"] == {"context": ".", "args": {"APP_VERSION": "${APP_VERSION:-dev}"}}


def test_guardrails_job_steps_pass_on_this_repo(tmp_path):
    """The guardrails job's `run:` steps in a fresh git repo of the app (scan-tree reads `git ls-files`)."""
    from conftest import copy_app, load_workflow, run
    root = copy_app(tmp_path)
    assert run(["git", "init", "-q", "-b", "main"], cwd=root).returncode == 0
    assert run(["git", "add", "-A"], cwd=root).returncode == 0
    env = dict(__import__("os").environ, PR_TITLE="feat(orders): name the service in healthz")
    steps = [s for s in load_workflow()["jobs"]["guardrails"]["steps"] if "run" in s]
    assert len(steps) == 3
    for step in steps:
        r = run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=root, env=env)
        assert r.returncode == 0, step["run"] + r.stdout + r.stderr
