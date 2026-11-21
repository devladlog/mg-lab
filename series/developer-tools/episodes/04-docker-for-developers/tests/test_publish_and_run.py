"""Run the Dockerfile's own build commands here (no Docker daemon), then start the published app the way the
final stage does: same ENTRYPOINT, same ENV, port from ASPNETCORE_HTTP_PORTS like the base image, a /data
folder standing in for the volume. Stop it with SIGTERM like `docker stop` and start it again."""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.request

import pytest

from conftest import APP, cl

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="needs the .NET SDK")


def dockerfile_commands(stages):
    """The RUN lines of the build stage, with BuildKit flags removed and $TARGETARCH filled in."""
    cmds = []
    for i in stages[0].instructions:
        if i.keyword == "RUN":
            for part in i.args.split("&&"):
                part = part.strip().replace("$TARGETARCH", "amd64")
                if part.startswith("dotnet "):
                    cmds.append(part)
    return cmds


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read() or b"null")


def wait_healthy(base, proc, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"app exited early: {proc.stdout.read()}")
        try:
            return call("GET", f"{base}/healthz")[1]
        except OSError:
            time.sleep(0.5)
    raise AssertionError("app did not become healthy")


@pytest.fixture(scope="module")
def published(tmp_path_factory, stages):
    work = tmp_path_factory.mktemp("image")
    src = work / "src"
    # Copy exactly the build context, as Docker would.
    for rel in cl.build_context(APP):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP / rel, src / rel)
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    for cmd in dockerfile_commands(stages):
        cmd = cmd.replace("-o /app", f"-o {work / 'app'}")
        res = subprocess.run(cmd.split(), cwd=src, env=env, capture_output=True, text=True, timeout=600)
        assert res.returncode == 0, f"{cmd}\n{res.stdout[-3000:]}"
    (work / "data").mkdir()
    return work


def start(work, stages, port):
    env_line = " ".join(i.args for i in stages[1].instructions if i.keyword == "ENV")
    image_env = dict(re.findall(r'(\w+)=("[^"]*"|\S+)', env_line))
    image_env = {k: v.strip('"').replace("/data/", f"{work / 'data'}/") for k, v in image_env.items()}
    entry = json.loads(next(i.args for i in stages[1].instructions if i.keyword == "ENTRYPOINT"))
    env = {"PATH": os.environ["PATH"], "HOME": str(work), "DOTNET_ROOT": os.environ.get("DOTNET_ROOT", ""),
           "ASPNETCORE_HTTP_PORTS": str(port), **image_env}
    return subprocess.Popen(entry, cwd=work / "app", env={k: v for k, v in env.items() if v},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_dockerfile_build_commands_are_restore_then_publish(stages):
    cmds = dockerfile_commands(stages)
    assert [c.split()[1] for c in cmds] == ["restore", "publish"]
    assert "--no-restore" in cmds[1] and "-c Release" in cmds[1]


def test_publish_output_has_the_entrypoint_and_no_sdk_leftovers(published):
    app = published / "app"
    assert (app / "Contoso.Orders.Api").exists() and os.access(app / "Contoso.Orders.Api", os.X_OK)
    assert (app / "Contoso.Orders.Api.dll").exists()
    assert not list(app.glob("*.cs")) and not (app / "obj").exists()


def test_runs_like_the_container_and_survives_a_restart(published, stages):
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(published, stages, port)
    try:
        health = wait_healthy(base, proc)
        assert health["status"] == "ok" and health["database"] == "Sqlite"
        status, created = call("POST", f"{base}/orders", {"customer": "Alex Demo", "total": 19.99})
        assert status == 201
    finally:
        proc.send_signal(signal.SIGTERM)          # what `docker stop` sends first
        out, _ = proc.communicate(timeout=30)
    assert proc.returncode == 0, out              # graceful shutdown, not killed
    assert "Application is shutting down" in out
    assert (published / "data" / "orders.db").exists()   # written to the "volume", not to /app

    proc = start(published, stages, port)          # new container, same volume
    try:
        wait_healthy(base, proc)
        status, again = call("GET", f"{base}/orders/{created['id']}")
        assert status == 200 and again["customer"] == "Alex Demo"
        assert call("GET", f"{base}/orders?page=1")[1]["total"] == 238   # seeded once, not twice
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=30)
