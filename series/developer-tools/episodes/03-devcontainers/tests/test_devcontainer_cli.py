"""The official Dev Containers CLI resolves our config: Features are downloaded from ghcr.io and merged with
the image's own metadata. Opt-in (needs network + the CLI):

    npm install --prefix /tmp/dccli @devcontainers/cli
    DEVCONTAINER_CLI=/tmp/dccli/node_modules/.bin/devcontainer python3 -m pytest tests/test_devcontainer_cli.py

There is no Docker daemon on the build machine. `read-configuration` only asks Docker whether a container
already exists (`docker ps`) and for local image metadata, so a stub `docker` that answers "nothing" is
enough; the CLI then reads the image metadata from the registry itself. `devcontainer up` / `build` need a
real Docker and are run on the recording laptop (demo.md).
"""
import json
import os
import subprocess

import pytest

from conftest import APP

CLI = os.environ.get("DEVCONTAINER_CLI")
pytestmark = pytest.mark.skipif(not CLI, reason="set DEVCONTAINER_CLI to the devcontainer CLI path")


@pytest.fixture(scope="module")
def resolved(tmp_path_factory):
    stub = tmp_path_factory.mktemp("stub") / "docker"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    res = subprocess.run([CLI, "read-configuration", "--workspace-folder", str(APP), "--docker-path", str(stub),
                          "--include-features-configuration", "--include-merged-configuration"],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_features_resolve_from_the_registry(resolved):
    feats = {f["id"]: f for s in resolved["featuresConfiguration"]["featureSets"] for f in s["features"]}
    assert set(feats) == {"python", "github-cli"}
    assert feats["python"]["value"] == {"version": "os-provided", "installTools": False}
    assert all(f["version"].split(".")[0] == "1" for f in feats.values())


def test_merged_configuration_shows_extensions_we_did_not_ask_for(resolved):
    merged = resolved["mergedConfiguration"]
    exts = [x for c in merged["customizations"]["vscode"] for x in c.get("extensions", [])]
    assert "dbaeumer.vscode-eslint" in exts          # from the image (node Feature baked in)
    assert "ms-python.python" in exts                 # from the Python Feature
    assert "-dbaeumer.vscode-eslint" in exts          # ...and our removal, applied last
    assert merged["postCreateCommands"] == ["bash .devcontainer/post-create.sh"]
    assert merged["remoteUser"] == "vscode"
