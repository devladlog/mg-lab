import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

import build_extension
import build_prompt_formula
import pytest
import sync_from_canvas
from conftest import SRC, pac


@pytest.fixture(scope="module")
def base():
    return json.loads(build_extension.BASE_SCHEMA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ext():
    return json.loads(build_extension.EXT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def files(base, ext):
    return build_extension.build(base, ext)


def test_base_schema_is_byte_identical_to_episode_12(schema):
    ep12 = SRC.parents[1] / "12-build-a-model-driven-app-from-start-to-end" / "src" / "schema" / "contosoinspections.schema.json"
    assert (SRC / "schema" / "contosoinspections.schema.json").read_bytes() == ep12.read_bytes()


def test_extension_adds_only_new_prefixed_columns_to_an_existing_base_table(base, ext):
    build_extension.check_extension(base, ext)
    assert [t["logicalName"] for t in ext["tables"]] == ["cin_inspectionitem"]
    assert ext["dependsOn"] == "ContosoInspections"


def test_extension_rejects_a_column_the_base_already_has(base, ext):
    bad = json.loads(json.dumps(ext))
    bad["tables"][0]["columns"][0]["logicalName"] = "cin_severity"
    with pytest.raises(ValueError, match="already exists"):
        build_extension.build(base, bad)
    bad = json.loads(json.dumps(ext))
    bad["tables"][0]["columns"][0]["logicalName"] = "ai_severity"
    with pytest.raises(ValueError, match="prefix"):
        build_extension.build(base, bad)
    bad = json.loads(json.dumps(ext))
    bad["tables"][0]["logicalName"] = "cin_nothing"
    with pytest.raises(ValueError, match="unknown base table"):
        build_extension.build(base, bad)


def test_generated_xml_is_well_formed_and_has_the_five_attributes_and_the_same_option_values_as_the_base(files, base):
    root = ET.fromstring(files["customizations.xml"])
    names = [a.get("PhysicalName") for a in root.iter("attribute")]
    assert names == ["cin_aiseverity", "cin_aiprovider", "cin_aiconfidence", "cin_aisummary", "cin_aiaccepted"]
    opt = next(a for a in root.iter("attribute") if a.get("PhysicalName") == "cin_aiseverity")
    values = [int(o.get("value")) for o in opt.iter("option")]
    assert values == [base["publisher"]["optionValuePrefix"] * 10000 + n for n in range(4)] == [455320000, 455320001, 455320002, 455320003]
    assert "<MaxValue>100</MaxValue>" in files["customizations.xml"] and "<MinValue>0</MinValue>" in files["customizations.xml"]


def test_solution_manifest_uses_the_base_publisher_and_only_includes_the_table_subcomponents(files, base):
    root = ET.fromstring(files["solution.xml"])
    assert root.findtext(".//SolutionManifest/UniqueName") == "ContosoInspectionsAI"
    assert root.findtext(".//Publisher/CustomizationPrefix") == "cin"
    rc = [dict(r.attrib) for r in root.iter("RootComponent")]
    assert rc == [{"type": "1", "schemaName": "cin_inspectionitem", "behavior": "1"}]


def test_the_committed_solution_source_is_what_pac_unpack_makes_from_the_generated_zip(tmp_path, files):
    z = tmp_path / "x.zip"
    build_extension.load_base().write_zip(files, z)
    code, out = pac("solution", "unpack", "--zipfile", z, "--folder", tmp_path / "un", "--packagetype", "Unmanaged")
    assert code == 0, out
    for rel in ("Other/Solution.xml", "Other/Customizations.xml", "Entities/cin_inspectionitem/Entity.xml"):
        assert (tmp_path / "un" / rel).read_bytes() == (SRC / "solution" / "ContosoInspectionsAI" / rel).read_bytes(), rel


def test_pack_of_the_committed_source_round_trips_with_no_rewrite_of_the_columns(tmp_path):
    code, out = pac("solution", "pack", "--zipfile", tmp_path / "p.zip", "--folder", SRC / "solution" / "ContosoInspectionsAI", "--packagetype", "Unmanaged")
    assert code == 0, out
    with zipfile.ZipFile(tmp_path / "p.zip") as z:
        assert "customizations.xml" in z.namelist() and "solution.xml" in z.namelist()
        assert z.read("customizations.xml").decode().count('PhysicalName="cin_ai') == 5


def test_generated_prompt_formula_and_custom_page_are_in_sync_with_their_sources():
    assert (SRC / "app" / "Src" / "App.ai-prompt.pa.yaml").read_text(encoding="utf-8") == build_prompt_formula.render((SRC / "prompts" / "system.md").read_text(encoding="utf-8"))
    assert (SRC / "custompage" / "Src" / "App.pa.yaml").read_text(encoding="utf-8") == sync_from_canvas.render_app()
    assert (SRC / "custompage" / "Src" / "TriagePage.pa.yaml").read_text(encoding="utf-8") == sync_from_canvas.render_screen()
