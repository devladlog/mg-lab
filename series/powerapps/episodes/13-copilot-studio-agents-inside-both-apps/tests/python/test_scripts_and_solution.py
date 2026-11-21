import re
import shutil
import xml.etree.ElementTree as ET

from conftest import EPISODES, SRC, pac, pwsh, table

PS1 = SRC / "scripts" / "Set-ColumnDescriptions.ps1"
SHELL = SRC / "solution" / "ContosoInspectionsAgent"


def test_schema_is_an_exact_copy_of_episodes_11_and_12():
    mine = (SRC / "schema" / "contosoinspections.schema.json").read_bytes()
    for ep in ("11-build-a-canvas-app-from-start-to-end", "12-build-a-model-driven-app-from-start-to-end"):
        assert (EPISODES / ep / "src" / "schema" / "contosoinspections.schema.json").read_bytes() == mine


def test_powershell_script_parses():
    code, out, err = pwsh("-Command", f"$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('{PS1}',[ref]$t,[ref]$e);$e.Count")
    assert code == 0 and out.strip() == "0", err + out


def test_plan_only_gets_then_puts_every_described_column_and_publishes(schema):
    import json
    n = sum(len(v) for v in json.loads((SRC / "data" / "column-descriptions.json").read_text(encoding="utf-8")).values())
    code, out, err = pwsh("-File", PS1, "-EnvironmentUrl", "https://contoso-dev.example", "-PlanOnly")
    assert code == 0, err
    lines = out.strip().splitlines()
    assert sum(l.startswith("GET ") for l in lines) == n and sum(l.startswith("PUT ") for l in lines) == n
    assert all("MergeLabels: true" in l for l in lines if l.startswith("PUT "))
    assert all("/Microsoft.Dynamics.CRM." not in l.split("   (")[0] for l in lines if l.startswith("PUT "))
    assert lines[-1].startswith("POST ") and "PublishXml" in lines[-1]
    assert "cin_inspectionitem" in lines[-1] and "cin_inspector" not in lines[-1]
    assert not any("cin_reviewernotes" in l for l in lines)


def test_script_never_signs_in_and_needs_a_token_to_write():
    text = PS1.read_text(encoding="utf-8")
    assert not re.search(r"az login|Connect-|Get-AzAccessToken|pac auth", text)
    code, out, err = pwsh("-File", PS1, "-EnvironmentUrl", "https://contoso-dev.example")
    assert code != 0 and "DATAVERSE_ACCESS_TOKEN" in (out + err)


def test_solution_shell_matches_the_schema_and_packs_round_trip(tmp_path, schema):
    m = ET.fromstring((SHELL / "Other" / "Solution.xml").read_text(encoding="utf-8-sig")).find("SolutionManifest")
    assert m.findtext("UniqueName") == "ContosoInspectionsAgent"
    pub = m.find("Publisher")
    assert pub.findtext("CustomizationPrefix") == schema["publisher"]["prefix"]
    assert int(pub.findtext("CustomizationOptionValuePrefix")) == schema["publisher"]["optionValuePrefix"]
    zip_ = tmp_path / "agent.zip"
    code, out = pac("solution", "pack", "--zipfile", zip_, "--folder", SHELL, "--packagetype", "Unmanaged")
    assert code == 0, out
    back = tmp_path / "unpacked"
    code, out = pac("solution", "unpack", "--zipfile", zip_, "--folder", back, "--packagetype", "Unmanaged")
    assert code == 0, out
    m2 = ET.fromstring((back / "Other" / "Solution.xml").read_text(encoding="utf-8-sig")).find("SolutionManifest")
    assert m2.findtext("UniqueName") == "ContosoInspectionsAgent" and m2.findtext("Version") == "1.0.0.0"
    shutil.rmtree(back)
