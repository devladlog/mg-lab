"""Run .devcontainer/post-create.sh for real, in a throwaway copy of the repo (no container needed:
the script only uses bash, git, python3 and dotnet, which this machine has too)."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import APP

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="needs the .NET SDK")


@pytest.fixture()
def repo(tmp_path):
    dst = tmp_path / "orders-app"
    shutil.copytree(APP, dst, ignore=shutil.ignore_patterns("bin", "obj", "__pycache__", "TestResults"))
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1",
           # keep using the machine's package cache, as the named volume does in the container
           "NUGET_PACKAGES": os.environ.get("NUGET_PACKAGES", str(Path.home() / ".nuget/packages")),
           "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    return dst, env


def run(cmd, cwd, env, check=True):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=check, timeout=300)


def test_post_create_installs_hooks_and_restores(repo):
    dst, env = repo
    run(["git", "init", "-q", "-b", "main"], dst, env)
    out = run(["bash", ".devcontainer/post-create.sh"], dst, env).stdout
    assert "Hooks: .githooks" in out
    assert "Dev container ready: dotnet 10." in out
    assert run(["git", "config", "core.hooksPath"], dst, env).stdout.strip() == ".githooks"
    assert (dst / "src/Contoso.Orders.Api/obj/project.assets.json").exists()
    assert (dst / "tests/Contoso.Orders.Api.Tests/obj/project.assets.json").exists()


def test_post_create_is_safe_to_run_twice(repo):
    dst, env = repo
    run(["git", "init", "-q", "-b", "main"], dst, env)
    run(["bash", ".devcontainer/post-create.sh"], dst, env)
    second = run(["bash", ".devcontainer/post-create.sh"], dst, env)
    assert second.returncode == 0 and "Dev container ready" in second.stdout


def test_hooks_from_episode_1_work_after_post_create(repo):
    dst, env = repo
    run(["git", "init", "-q", "-b", "main"], dst, env)
    run(["bash", ".devcontainer/post-create.sh"], dst, env)
    run(["git", "config", "user.name", "Alex Demo"], dst, env)
    run(["git", "config", "user.email", "alex.demo@contoso.com"], dst, env)
    run(["git", "switch", "-q", "-c", "feature/devcontainer"], dst, env)
    run(["git", "add", ".devcontainer"], dst, env)
    bad = run(["git", "commit", "-m", "added container"], dst, env, check=False)
    assert bad.returncode != 0 and "commit message rejected" in bad.stderr
    good = run(["git", "commit", "-m", "build(devcontainer): add .NET 10 dev container"], dst, env, check=False)
    assert good.returncode == 0, good.stderr


def test_without_git_the_script_still_finishes(repo):
    dst, env = repo   # no git init: e.g. a downloaded zip
    out = run(["bash", ".devcontainer/post-create.sh"], dst, env).stdout
    assert "skipping hook setup" in out and "Dev container ready" in out


def test_a_failing_step_stops_the_script(repo):
    dst, env = repo
    (dst / "OrdersApp.slnx").unlink()    # dotnet restore must fail, and set -e must stop the script
    res = run(["bash", ".devcontainer/post-create.sh"], dst, env, check=False)
    assert res.returncode != 0
    assert "Dev container ready" not in res.stdout


@pytest.fixture()
def world_tmp():
    """pytest's tmp_path sits under a 0700 folder that 'nobody' cannot enter."""
    path = Path(tempfile.mkdtemp(prefix="ep03-"))
    path.chmod(0o777)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.mark.skipif(os.geteuid() != 0 or shutil.which("setpriv") is None,
                    reason="needs root + setpriv to run the script as an unprivileged user")
def test_root_owned_volume_is_handed_to_the_non_root_user(world_tmp):
    """Docker creates a new named volume owned by root. As the non-root remoteUser, the script must chown it.
    Here: a root-owned NuGet folder, the script run as 'nobody', and a recording `sudo` and `dotnet` on PATH
    (the real ones are exercised by the tests above; this one is about the ownership branch only)."""
    tmp_path = world_tmp
    dst = tmp_path / "orders-app"
    shutil.copytree(APP, dst, ignore=shutil.ignore_patterns("bin", "obj", "__pycache__", "TestResults"))
    nuget = tmp_path / "nuget"
    nuget.mkdir(mode=0o755)                       # owned by root, not writable by nobody
    fakebin, home, log = tmp_path / "bin", tmp_path / "home", tmp_path / "calls.log"
    fakebin.mkdir()
    home.mkdir()
    log.touch()
    (fakebin / "sudo").write_text(f'#!/bin/sh\necho "sudo $*" >> {log}\n')
    (fakebin / "dotnet").write_text('#!/bin/sh\n[ "$1" = "--version" ] && echo 10.0.404\nexit 0\n')
    for p in (fakebin / "sudo", fakebin / "dotnet"):
        p.chmod(0o755)
    for p in [tmp_path, home, log, *dst.rglob("*"), dst]:
        p.chmod(p.stat().st_mode | 0o777 if p.is_dir() else p.stat().st_mode | 0o666)
    env = {"PATH": f"{fakebin}:/usr/bin:/bin", "HOME": str(home), "NUGET_PACKAGES": str(nuget)}
    res = subprocess.run(["setpriv", "--reuid=65534", "--regid=65534", "--clear-groups",
                          "bash", ".devcontainer/post-create.sh"],
                         cwd=dst, env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert f"Taking ownership of {nuget}" in res.stdout
    assert log.read_text().strip() == f"sudo chown -R 65534:65534 {nuget}"
