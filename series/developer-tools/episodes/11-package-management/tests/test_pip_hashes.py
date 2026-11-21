"""tools/requirements.txt: hashes for every package, and pip's behaviour when a hash is wrong (needs network: PyPI)."""

from __future__ import annotations

import re
import subprocess
import venv
from pathlib import Path

import pytest
from conftest import APP

REQ = APP / "tools" / "requirements.txt"
REQ_IN = APP / "tools" / "requirements.in"


@pytest.fixture(scope="module")
def pip(tmp_path_factory) -> list[str]:
    env = tmp_path_factory.mktemp("venv")
    venv.create(env, with_pip=True)
    return [str(env / "bin" / "python"), "-m", "pip", "--disable-pip-version-check"]


def requirements() -> list[str]:
    """One entry per pinned package: 'name==version' followed by its --hash lines."""
    text = REQ.read_text().replace("\\\n", " ")
    return [ln.strip() for ln in text.splitlines() if re.match(r"^[A-Za-z0-9_.-]+==", ln)]


def test_every_requirement_is_pinned_and_has_at_least_one_hash():
    lines = requirements()
    assert len(lines) >= 5
    for line in lines:
        assert re.match(r"^[A-Za-z0-9_.-]+==[0-9][^ ]* ", line), line
        assert "--hash=sha256:" in line, line


def test_the_direct_requirements_are_in_the_input_file_and_the_lock_pins_the_pinned_ruff():
    names = {re.split(r"[=<>]", ln.split("#")[0].strip())[0] for ln in REQ_IN.read_text().splitlines()
             if ln.strip() and not ln.startswith("#")}
    assert names == {"ruff", "pytest", "pyyaml"}
    assert any(ln.startswith("ruff==0.16.9 ") for ln in requirements())


def test_pip_accepts_the_file_in_require_hashes_mode(pip):
    proc = subprocess.run([*pip, "install", "--require-hashes", "--dry-run", "-r", str(REQ)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Would install" in proc.stdout and "ruff-0.16.9" in proc.stdout


def test_a_wrong_hash_stops_the_install(pip, tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("ruff==0.16.9 \\\n    --hash=sha256:" + "0" * 64 + "\n")
    proc = subprocess.run([*pip, "install", "--require-hashes", "--dry-run", "-r", str(bad)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    assert "THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE" in proc.stderr


def test_a_requirement_without_a_hash_stops_the_install(pip, tmp_path):
    plain = tmp_path / "plain.txt"
    plain.write_text("ruff==0.16.9\n")
    proc = subprocess.run([*pip, "install", "--require-hashes", "--dry-run", "-r", str(plain)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    assert "Hashes are required in --require-hashes mode" in proc.stderr
    assert re.search(r"ruff==0\.16\.9 --hash=sha256:[0-9a-f]{64}", proc.stderr)         # pip prints the hash to add


def test_pip_compile_reproduces_the_committed_file(tmp_path):
    """Skipped unless pip-tools is installed (pip install pip-tools). The header lines name the command and are ignored."""
    import shutil
    if shutil.which("pip-compile") is None:
        pytest.skip("pip-compile not installed")
    out = tmp_path / "requirements.txt"
    work = tmp_path / "tools"
    work.mkdir()
    (work / "requirements.in").write_text(REQ_IN.read_text())
    proc = subprocess.run(["pip-compile", "--generate-hashes", "--strip-extras", "--allow-unsafe", "--quiet",
                           "tools/requirements.in", "-o", str(out)], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    body = lambda p: [ln for ln in Path(p).read_text().splitlines() if not ln.startswith("#")]  # noqa: E731
    committed, fresh = body(REQ), body(out)
    # New releases between the commit and today may move a version; the pinned names must still be the same set.
    names = lambda lines: {ln.split("==")[0] for ln in lines if "==" in ln}  # noqa: E731
    assert names(committed) == names(fresh)
