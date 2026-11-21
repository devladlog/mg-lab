import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from conftest import FAST, SRC, actions, needs_pac, needs_pwsh
from flowkit.lint import lint, load_flow

SOL = SRC / "solution"


def test_flow_lints_clean_in_flowkit():
    for path in (FAST, SRC / "drafts" / "slow-archive-done-requests.json"):
        findings = lint(load_flow(path))
        assert not [f for f in findings if f.level == "error"], findings


def test_solution_metadata():
    root = ET.parse(SOL / "Other" / "Solution.xml").getroot()
    m = root.find("SolutionManifest")
    assert m.find("UniqueName").text == "ITHousekeeping"
    assert m.find("Version").text == "1.0.0.0"
    assert m.find("Managed").text == "0"


def test_env_vars_and_connection_refs():
    text = " ".join(p.read_text() for p in SOL.rglob("*") if p.is_file() and p.suffix in {".xml", ".json"})
    for name in ("cts_ITSiteUrl", "cts_ITRequestsList", "cts_ArchiveAfterDays", "cts_ServiceDeskMailbox",
                 "cts_sharedsharepointonline_ithousekeeping", "cts_sharedoffice365_ithousekeeping"):
        assert name in text


def test_no_real_identifiers():
    bad = re.compile(r"devladlog|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    for p in (SRC).rglob("*"):
        if p.is_file() and p.suffix in {".json", ".xml", ".py", ".ps1", ".yml"} and "flowkit" not in p.parts:
            for m in bad.findall(p.read_text()):
                assert m.startswith("00000000-0000-0000-0000-") or m.lower() not in ("devladlog",), (p, m)


def test_build_is_deterministic(tmp_path):
    before = {p: p.read_bytes() for p in SOL.rglob("*") if p.is_file()}
    subprocess.run(["python", "tools/build_solution.py"], cwd=SRC, check=True, capture_output=True)
    after = {p: p.read_bytes() for p in SOL.rglob("*") if p.is_file()}
    assert before == after


@needs_pac
def test_pac_packs_the_solution(tmp_path):
    # the source folder is Managed=0, so pack as Unmanaged (a Managed pack of an unmanaged folder fails, see ep 9)
    out = tmp_path / "ITHousekeeping.zip"
    r = subprocess.run(["pac", "solution", "pack", "--zipfile", str(out), "--folder", str(SOL), "--packagetype", "Unmanaged"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.exists() and out.stat().st_size > 1000


def test_seed_script_parses():
    import shutil as sh
    if sh.which("pwsh") is None:
        import pytest
        pytest.skip("pwsh not installed")
    cmd = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
           f"'{SRC / 'scripts' / 'Seed-ITRequests.ps1'}',[ref]$t,[ref]$e);if($e){{$e;exit 1}}")
    assert subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True).returncode == 0
