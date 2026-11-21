"""ruff.toml and the `quality` job's Python steps, with the real ruff: the repo's own tools are clean, and a
"bad pull request" (one file, twelve findings) shows what is annotated, what --fix repairs and what stays for a human."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from conftest import APP, FIXTURES, copy_app, load_workflow

pytestmark = pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
PIN = next(re.search(r"ruff==([\d.]+)", s["run"]).group(1)
           for s in load_workflow()["jobs"]["quality"]["steps"] if "ruff==" in s.get("run", ""))
ANNOTATION = re.compile(r"::error title=ruff \((\w+)\),file=\S+?,line=(\d+),")


def ruff(root, *args):
    return subprocess.run(["ruff", *args, "--no-cache"], cwd=root, capture_output=True, text=True)


def codes(output: str) -> set[str]:
    return {m.group(1) for m in ANNOTATION.finditer(output)}


@pytest.fixture(scope="module")
def bad_pr(tmp_path_factory):
    version = subprocess.run(["ruff", "--version"], capture_output=True, text=True).stdout.split()[1]
    if version != PIN:
        pytest.skip(f"ruff {version} installed, the workflow pins {PIN}: rule sets differ between versions")
    root = copy_app(tmp_path_factory.mktemp("py"))
    shutil.copy(FIXTURES / "bad_report.py", root / "tools" / "bad_report.py")
    steps = {"check": ruff(root, "check", "--output-format", "github", "."),
             "format_check": ruff(root, "format", "--check", ".")}
    steps["fix"] = ruff(root, "check", "--fix", ".")                         # default output: ends with a summary
    steps["remaining"] = ruff(root, "check", "--output-format", "github", ".")
    steps["format"] = ruff(root, "format", ".")
    steps["after"] = (root / "tools" / "bad_report.py").read_text()
    steps["format_after"] = ruff(root, "format", "--check", ".")
    return root, steps


def test_the_tools_of_this_repo_pass_both_ruff_steps_of_the_quality_job(tmp_path):
    root = copy_app(tmp_path)
    assert ruff(root, "check", "--output-format", "github", ".").returncode == 0
    assert ruff(root, "format", "--check", ".").returncode == 0


def test_the_bad_file_is_annotated_with_the_rule_and_the_line(bad_pr):
    _, s = bad_pr
    assert s["check"].returncode == 1
    assert codes(s["check"].stdout) == {"E401", "I001", "F401", "UP035", "S105", "B006", "SIM108", "E712", "SIM115",
                                        "UP006"}
    assert "::error title=ruff (S105),file=" in s["check"].stdout and ",line=5," in s["check"].stdout


def test_fix_repairs_imports_and_annotations_but_leaves_the_judgement_calls(bad_pr):
    _, s = bad_pr
    after = s["after"]
    assert "import os\n\nAPI_PASSWORD" in after and "import sys" not in after and "import json" not in after
    assert "def names(items: list[str]) -> list[str]:" in after
    assert "Found 12 errors (6 fixed, 6 remaining)." in s["fix"].stdout + s["fix"].stderr
    assert "4 hidden fixes can be enabled with the `--unsafe-fixes` option" in s["fix"].stdout + s["fix"].stderr
    assert codes(s["remaining"].stdout) == {"S105", "B006", "SIM108", "E712", "SIM115"}   # a person decides these
    assert "seen=[]" in after and "== True" in after                                    # not touched


def test_format_is_a_separate_check_and_a_separate_fix(bad_pr):
    _, s = bad_pr
    assert s["format_check"].returncode == 1 and "1 file would be reformatted" in s["format_check"].stdout
    assert s["format"].stdout.strip() == "1 file reformatted, 9 files left unchanged"
    assert s["format"].returncode == 0 and '{"path": path, "data": data, "flag": flag}' in s["after"]
    assert s["format_after"].returncode == 0


def test_the_workflow_pin_vs_the_editor_and_the_config():
    assert "charliermarsh.ruff" in (APP / ".vscode" / "extensions.json").read_text()
    settings = (APP / ".vscode" / "settings.json").read_text()
    stripped = re.sub(r"^\s*//.*$", "", settings, flags=re.M)
    cfg = json.loads(re.sub(r",(\s*[}\]])", r"\1", stripped))                 # JSON with comments and trailing commas
    py = cfg["[python]"]
    assert py["editor.defaultFormatter"] == "charliermarsh.ruff"
    assert py["editor.codeActionsOnSave"] == {"source.fixAll": "explicit", "source.organizeImports": "explicit"}
    toml = (APP / "ruff.toml").read_text()
    assert 'select = ["E", "W", "F", "I", "B", "UP", "SIM", "S"]' in toml


def test_the_hand_fixed_version_passes_both_steps(tmp_path):
    root = copy_app(tmp_path)
    shutil.copy(FIXTURES / "bad_report.fixed.py", root / "tools" / "bad_report.py")
    assert ruff(root, "check", "--output-format", "github", ".").returncode == 0
    assert ruff(root, "format", "--check", ".").returncode == 0
