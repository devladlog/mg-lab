"""The Dataflow Gen2 item folder: generated from the queries, shaped like Learn's "Dataflow definition", parseable."""
import json
import re
import subprocess
import sys
import uuid

import pytest

from conftest import SRC, schema_errors

ITEM = SRC / "dataflow" / "ContosoBikesPrep.Dataflow"
CONTRACT = json.loads((SRC / "dataflow" / "contract.json").read_text(encoding="utf-8"))
PQ_LINT = SRC / "pq-lint" / "dist" / "src" / "cli.js"
needs_pq_lint = pytest.mark.skipif(not PQ_LINT.exists(), reason="build pq-lint first: cd src/pq-lint && npm ci && npm run build")


def metadata():
    return json.loads((ITEM / "queryMetadata.json").read_text(encoding="utf-8"))


def shared_names():
    return re.findall(r"(?m)^shared (\w+) =$", (ITEM / "mashup.pq").read_text(encoding="utf-8"))


def test_item_folder_matches_the_queries():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_dataflow.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_the_item_has_exactly_the_documented_parts_plus_the_platform_file():
    assert sorted(p.name for p in ITEM.iterdir()) == [".platform", "mashup.pq", "queryMetadata.json"]


def test_platform_file_validates_against_the_published_schema():
    doc = json.loads((ITEM / ".platform").read_text(encoding="utf-8"))
    assert not schema_errors(doc)
    assert doc["metadata"] == {"type": "Dataflow", "displayName": "Contoso Bikes Prep",
                               "description": "Prepares the Contoso Bikes exports once, for every semantic model."}
    assert doc["config"]["logicalId"] == "00000000-0000-0000-0000-000000000000"


def test_query_metadata_uses_the_fields_learn_documents():
    m = metadata()
    assert m["formatVersion"] == "202502"                       # "The only allowed value is 202502"
    assert set(m) <= {"formatVersion", "name", "computeEngineSettings", "queryGroups", "documentLocale", "gatewayObjectId",
                      "queriesMetadata", "connections", "fastCombine", "allowNativeQueries",
                      "skipAutomaticTypeAndHeaderDetection", "parametric"}
    assert m["name"] == "Contoso Bikes Prep"
    for q in m["queriesMetadata"].values():
        assert set(q) == {"queryId", "queryName", "queryGroupId", "isHidden", "loadEnabled"}
        uuid.UUID(q["queryId"])


def test_every_shared_member_has_metadata_and_the_other_way_round():
    assert sorted(shared_names()) == sorted(metadata()["queriesMetadata"])
    assert {q["queryName"] for q in metadata()["queriesMetadata"].values()} == set(metadata()["queriesMetadata"])


def test_query_ids_are_unique_and_groups_resolve():
    m = metadata()
    ids = [q["queryId"] for q in m["queriesMetadata"].values()]
    assert len(ids) == len(set(ids))
    groups = {g["id"]: g["name"] for g in m["queryGroups"]}
    assert [g["name"] for g in m["queryGroups"]] == ["Parameters", "Staging", "Output"]
    assert all(q["queryGroupId"] in groups for q in m["queriesMetadata"].values())


def test_only_the_contract_entities_load():
    loaded = {n for n, q in metadata()["queriesMetadata"].items() if q["loadEnabled"]}
    assert loaded == set(CONTRACT["entities"])
    for name in CONTRACT["staging"] + CONTRACT["parameters"]:
        assert metadata()["queriesMetadata"][name]["loadEnabled"] is False


def test_mashup_is_one_section_with_parameters_and_functions_first():
    text = (ITEM / "mashup.pq").read_text(encoding="utf-8")
    assert text.startswith("section Section1;\n")
    names = shared_names()
    assert names[:3] == ["ExportSite", "fnReadExport", "fnDimension"]
    assert names[3] == "SalesExport"
    assert names[4:] == list(CONTRACT["entities"])
    assert "IsParameterQuery = true" in text


def test_nothing_in_the_dataflow_needs_a_gateway_or_a_local_path():
    text = re.sub(r"(?m)^\s*//.*$", "", (ITEM / "mashup.pq").read_text(encoding="utf-8"))      # comments may mention them
    assert "File.Contents" not in text and "Folder.Files" not in text and "C:\\" not in text
    assert "SharePoint.Files(ExportSite" in text


@needs_pq_lint
def test_mashup_parses_as_a_section_document():
    r = subprocess.run(["node", str(PQ_LINT), "--section", str(ITEM / "mashup.pq")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "10 shared members" in r.stdout


@needs_pq_lint
def test_the_parser_rejects_a_broken_section(tmp_path):
    broken = (ITEM / "mashup.pq").read_text(encoding="utf-8").replace("in\n    Typed;", "Typed;", 1)
    f = tmp_path / "broken.pq"
    f.write_text(broken, encoding="utf-8")
    r = subprocess.run(["node", str(PQ_LINT), "--section", str(f)], capture_output=True, text=True)
    assert r.returncode == 1 and "PQ001" in r.stdout


@needs_pq_lint
def test_pq_lint_is_clean_on_the_dataflow_queries():
    r = subprocess.run(["node", str(PQ_LINT), str(SRC / "dataflow" / "queries"), "--strict"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "10 queries: 0 error(s), 0 warning(s)" in r.stdout
