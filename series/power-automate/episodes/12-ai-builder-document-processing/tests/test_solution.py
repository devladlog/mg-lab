"""The solution folder is consistent, lints clean and packs with the real Power Platform CLI (no sign-in)."""
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from conftest import SOLUTION, SRC, needs_pac

from flowkit.lint import lint, load_flow

FLOW_FILE = next((SOLUTION / "Workflows").glob("Triageinvoiceextraction-*.json"))


def test_flow_lints_clean():
    assert [f for f in lint(load_flow(FLOW_FILE)) if f.level == "error"] == []


def test_environment_variables_match_what_the_flow_uses():
    defs = sorted(p.name for p in (SOLUTION / "environmentvariabledefinitions").iterdir())
    flow = load_flow(FLOW_FILE)
    params = flow["properties"]["definition"]["parameters"]
    in_flow = sorted(v["metadata"]["schemaName"] for k, v in params.items() if k.startswith("$") is False)
    assert defs == in_flow and len(defs) == 7
    text = FLOW_FILE.read_text("utf-8")
    for k in params:
        if not k.startswith("$"):
            assert f"parameters('{k}')" in text, f"{k} is declared but never used"


def test_nothing_environment_specific_is_typed_into_the_flow():
    flow = load_flow(FLOW_FILE)["properties"]["definition"]
    body = json.dumps({"triggers": flow["triggers"], "actions": flow["actions"]})   # the parameter defaults may hold placeholders
    assert "sharepoint.com" not in body and "@contoso.com" not in body and "https://" not in body


def test_connection_references_are_declared_and_used():
    flow = load_flow(FLOW_FILE)
    refs = flow["properties"]["connectionReferences"]
    assert sorted(refs) == ["shared_office365", "shared_sharepointonline"]
    cust = ET.parse(SOLUTION / "Other" / "Customizations.xml").getroot()
    declared = {e.get("connectionreferencelogicalname") for e in cust.iter("connectionreference")}
    assert declared == {v["connection"]["connectionReferenceLogicalName"] for v in refs.values()}


def test_solution_xml_identity():
    root = ET.parse(SOLUTION / "Other" / "Solution.xml").getroot()
    m = root.find("SolutionManifest")
    assert m.findtext("UniqueName") == "ITInvoiceIntake" and m.findtext("Version") == "1.0.0.0"
    assert m.find("Publisher").findtext("CustomizationPrefix") == "cts" and m.findtext("Managed") == "2"


def test_build_script_is_idempotent():
    before = {p: p.read_bytes() for p in SOLUTION.rglob("*") if p.is_file()}
    r = subprocess.run(["python3", str(SRC / "tools" / "build_solution.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    after = {p: p.read_bytes() for p in SOLUTION.rglob("*") if p.is_file()}
    assert before == after


@needs_pac
def test_pac_packs_managed_and_unmanaged_and_lists_the_variables(tmp_path):
    for kind, flag in (("Unmanaged", "0"), ("Managed", "1")):
        z = tmp_path / f"{kind}.zip"
        r = subprocess.run(["pac", "solution", "pack", "--zipfile", str(z), "--folder", str(SOLUTION), "--packagetype", kind],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"<Managed>{flag}</Managed>" in zipfile.ZipFile(z).read("solution.xml").decode("utf-8-sig")
    out = tmp_path / "s.json"
    r = subprocess.run(["pac", "solution", "create-settings", "--solution-folder", str(SOLUTION), "--settings-file", str(out)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    gen = json.loads(out.read_text("utf-8"))
    assert sorted(e["SchemaName"] for e in gen["EnvironmentVariables"]) == sorted(p.name for p in (SOLUTION / "environmentvariabledefinitions").iterdir())
    assert len(gen["ConnectionReferences"]) == 2
