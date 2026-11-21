"""Checks against the Power Platform CLI (no sign-in needed; skipped without `pac`)."""
import json
import shutil
import subprocess
import zipfile

import pytest

from conftest import CONNECTOR, SOLUTION

needs_pac = pytest.mark.skipif(shutil.which("pac") is None, reason="pac CLI not installed")


def shape(node):
    """Keys and types only: drop the text that makers write."""
    if isinstance(node, dict):
        return {k: shape(v) for k, v in node.items() if k not in ("displayName", "description", "tooltip")}
    return type(node).__name__


@needs_pac
def test_connection_parameters_have_the_shape_pac_connector_init_generates(tmp_path):
    proc = subprocess.run(["pac", "connector", "init", "--connection-template", "BasicAuth", "--generate-settings-file",
                           "--outputDirectory", str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated = json.loads((tmp_path / "apiProperties.json").read_text())["properties"]["connectionParameters"]
    ours = json.loads((CONNECTOR / "apiProperties.json").read_text())["properties"]["connectionParameters"]
    assert shape(ours) == shape(generated)
    assert set(json.loads((tmp_path / "settings.json").read_text())) == set(json.loads((CONNECTOR / "settings.json").read_text()))


@needs_pac
def test_pac_solution_pack(tmp_path):
    out = tmp_path / "GitHubIntake.zip"
    proc = subprocess.run(["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOLUTION), "--packagetype", "Unmanaged"],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = zipfile.ZipFile(out).namelist()
    assert "solution.xml" in names and "customizations.xml" in names
    assert sum(n.startswith("Workflows/") and n.endswith(".json") for n in names) == 1
    env = sorted(n.split("/")[1] for n in names if n.startswith("environmentvariabledefinitions/"))
    assert env == ["cts_GitHubOwner", "cts_GitHubRepo", "cts_HelpdeskSiteUrl"]
