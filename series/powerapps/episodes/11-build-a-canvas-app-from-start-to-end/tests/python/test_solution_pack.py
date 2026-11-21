"""The solution shell (src/solution/ContosoInspections) and the real Power Platform CLI, offline: pac solution pack and unpack."""
import re
import xml.etree.ElementTree as ET
import zipfile

from conftest import SOLUTION, pac


def solution_xml(path):
    return ET.fromstring(path.read_text(encoding="utf-8-sig"))


def test_solution_xml_matches_the_schema(schema):
    root = solution_xml(SOLUTION / "Other" / "Solution.xml")
    m = root.find("SolutionManifest")
    assert m.findtext("UniqueName") == schema["solution"]["uniqueName"]
    assert m.findtext("Version") == schema["version"]
    assert m.find("LocalizedNames/LocalizedName").get("description") == schema["solution"]["displayName"]
    assert m.find("Descriptions/Description").get("description") == schema["solution"]["description"]
    pub = m.find("Publisher")
    assert pub.findtext("UniqueName") == schema["publisher"]["uniqueName"]
    assert pub.findtext("CustomizationPrefix") == schema["publisher"]["prefix"]
    assert int(pub.findtext("CustomizationOptionValuePrefix")) == schema["publisher"]["optionValuePrefix"]
    assert pub.find("Descriptions/Description").get("description") == schema["publisher"]["description"]


def test_the_shell_does_not_hand_write_entities_or_roles():
    # Learn (solution file reference): editing Entities, Attributes and Security Roles in customizations.xml is unsupported.
    # The tables and the role come from the schema script through the Web API, then `pac solution export` + unpack.
    root = ET.fromstring((SOLUTION / "Other" / "Customizations.xml").read_text(encoding="utf-8-sig"))
    assert list(root.find("Entities")) == []
    assert list(root.find("Roles")) == []
    assert not (SOLUTION / "Entities").exists()


def pack(tmp_path, packagetype="Unmanaged"):
    # `unpack --packagetype Both` looks for <name>.zip and <name>_managed.zip side by side (what an export of both types gives).
    out = tmp_path / ("ContosoInspections_1_0_0_0_managed.zip" if packagetype == "Managed" else "ContosoInspections_1_0_0_0.zip")
    r = pac("solution", "pack", "--zipfile", out, "--folder", SOLUTION, "--packagetype", packagetype)
    assert r.code == 0, r
    return out


def test_pack_writes_a_zip_with_the_solution_files(tmp_path):
    z = zipfile.ZipFile(pack(tmp_path))
    assert {"solution.xml", "customizations.xml", "[Content_Types].xml"} <= set(z.namelist())
    assert "<UniqueName>ContosoInspections</UniqueName>" in z.read("solution.xml").decode("utf-8-sig")


def test_pack_as_managed_marks_the_solution_managed(tmp_path):
    z = zipfile.ZipFile(pack(tmp_path, "Managed"))
    assert "<Managed>1</Managed>" in z.read("solution.xml").decode("utf-8-sig")


def test_pack_then_unpack_gives_back_the_same_source(tmp_path):
    target = tmp_path / "unpacked"
    unmanaged, _managed = pack(tmp_path), pack(tmp_path, "Managed")
    r = pac("solution", "unpack", "--zipfile", unmanaged, "--folder", target, "--packagetype", "Both")
    assert r.code == 0, r
    mine = sorted(p.relative_to(SOLUTION).as_posix() for p in SOLUTION.rglob("*") if p.is_file())
    theirs = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
    assert theirs == mine
    for rel in mine:
        assert (target / rel).read_bytes() == (SOLUTION / rel).read_bytes(), rel


def test_a_solution_version_bump_changes_the_zip_name_pattern_not_the_source_layout(tmp_path, source_copy):
    text = (source_copy / "Other" / "Solution.xml").read_text(encoding="utf-8")
    (source_copy / "Other" / "Solution.xml").write_text(text.replace("<Version>1.0.0.0</Version>", "<Version>1.1.0.0</Version>"), encoding="utf-8")
    out = tmp_path / "bumped.zip"
    assert pac("solution", "pack", "--zipfile", out, "--folder", source_copy, "--packagetype", "Unmanaged").code == 0
    assert re.search(r"<Version>1\.1\.0\.0</Version>", zipfile.ZipFile(out).read("solution.xml").decode("utf-8-sig"))


def test_a_broken_solution_xml_fails_to_pack(tmp_path, source_copy):
    (source_copy / "Other" / "Solution.xml").write_text("<ImportExportXml><SolutionManifest>", encoding="utf-8")
    r = pac("solution", "pack", "--zipfile", tmp_path / "bad.zip", "--folder", source_copy, "--packagetype", "Unmanaged")
    assert r.code != 0
