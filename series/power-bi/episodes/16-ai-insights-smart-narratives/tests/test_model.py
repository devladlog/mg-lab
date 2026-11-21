"""The TMDL model and the PBIP: static checks only. No DAX engine runs here, so measures are checked for structure and references."""
import csv
import json
import re

import pytest

import build_order_profile as bop
from conftest import MODEL, SRC, schema_errors

TABLES = {p.stem: p.read_text(encoding="utf-8") for p in (MODEL / "tables").glob("*.tmdl")}


def names(text, kind):
    return {n.strip("'").replace("''", "'") for n in re.findall(rf"^\t{kind}\s+('(?:[^']|'')+'|[^\s=]+)", text, flags=re.M)}


COLUMNS = {t: names(x, "column") for t, x in TABLES.items()}
MEASURES = {t: names(x, "measure") for t, x in TABLES.items()}
ALL_MEASURES = set().union(*MEASURES.values())


def test_model_does_not_discourage_implicit_measures():
    """Key influencers does not support a categorical metric when this is on (Learn), so this model leaves it off."""
    assert "discourageImplicitMeasures" not in (MODEL / "model.tmdl").read_text(encoding="utf-8")


def test_every_table_is_referenced_by_the_model():
    refs = {m.strip("'") for m in re.findall(r"^ref table (.+)$", (MODEL / "model.tmdl").read_text(encoding="utf-8"), flags=re.M)}
    assert refs == set(TABLES) == {"Sales", "Order Profile", "Date", "Product", "Customer", "Store"}


def test_every_measure_has_a_description_and_a_display_folder():
    for table, text in TABLES.items():
        for m in re.finditer(r"((?:^\t///.*\n)*)^\tmeasure\s+('(?:[^']|'')+'|[^\s=]+)", text, flags=re.M):
            assert m.group(1).strip(), f"{table}: measure {m.group(2)} has no /// description"
    for table in ("Sales", "Order Profile"):
        blocks = re.split(r"(?=^\tmeasure )", TABLES[table], flags=re.M)[1:]
        for b in blocks:
            head = re.split(r"\n\n|\n\tcolumn|\n\tpartition", b)[0]
            assert "displayFolder:" in head, head[:60]


@pytest.mark.parametrize("table", ["Sales", "Order Profile"])
def test_references_resolve(table):
    text = TABLES[table].split("\tpartition ")[0]   # the partition holds Power Query, where [..] means something else
    for m in re.finditer(r"'?([A-Za-z][A-Za-z ]*?)'?\[([^\]]+)\]", text):
        tbl, name = m.group(1).strip(), m.group(2)
        if tbl in TABLES:
            assert name in COLUMNS[tbl] | MEASURES[tbl], f"{table}: {tbl}[{name}] does not exist"
    body = re.sub(r"^\t///.*$", "", text, flags=re.M)
    for name in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", body):
        assert name in ALL_MEASURES, f"{table}: measure [{name}] does not exist"


def test_order_profile_columns_match_the_csv_header():
    mapped = re.findall(r"^\t\tsourceColumn: (\w+)$", TABLES["Order Profile"], flags=re.M)
    assert mapped == bop.FIELDS
    typed = re.findall(r'\{"(\w+)", ', TABLES["Order Profile"])
    assert sorted(typed) == sorted(bop.FIELDS)


def test_order_profile_has_a_unique_key_column():
    assert re.search(r"column 'Order Number'\n\t\tdataType: string\n\t\tisKey", TABLES["Order Profile"])


def test_relationship_to_date_exists_and_targets_real_columns():
    rel = (MODEL / "relationships.tmdl").read_text(encoding="utf-8")
    assert "relationship 'Order Profile to Date'\n\tfromColumn: 'Order Profile'.'Order Date'\n\ttoColumn: Date.Date" in rel
    assert "Order Date" in COLUMNS["Order Profile"] and "Date" in COLUMNS["Date"]


def test_narrative_measures_are_all_text_returning():
    narrative = [m for m in MEASURES["Sales"] if m.startswith("Narrative")]
    assert sorted(narrative) == ["Narrative Sales", "Narrative Top Category", "Narrative YoY"]
    for m in narrative:
        block = re.search(rf"measure '{m}' =(.*?)(?=\n\t(?:///|measure|column)|\Z)", TABLES["Sales"], flags=re.S).group(1)
        assert '"' in block and "displayFolder: Narrative" in block


def test_tmdl_uses_tabs_only():
    for text in list(TABLES.values()) + [(MODEL / "model.tmdl").read_text(encoding="utf-8")]:
        for line in text.split("\n"):
            assert not line.startswith(" "), line


@pytest.mark.parametrize("path", [SRC / "ContosoSalesAI.pbip", SRC / "ContosoSalesAI.SemanticModel/definition.pbism",
                                  *sorted((SRC / "ContosoSalesAI.Report").rglob("*.json")), SRC / "ContosoSalesAI.Report/definition.pbir"],
                         ids=lambda p: str(p.relative_to(SRC)))
def test_project_files_match_their_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_pbip_points_at_the_report_and_the_report_at_the_model():
    pbip = json.loads((SRC / "ContosoSalesAI.pbip").read_text(encoding="utf-8"))
    assert pbip["artifacts"][0]["report"]["path"] == "ContosoSalesAI.Report"
    pbir = json.loads((SRC / "ContosoSalesAI.Report/definition.pbir").read_text(encoding="utf-8"))
    assert (SRC / "ContosoSalesAI.Report" / pbir["datasetReference"]["byPath"]["path"]).resolve() == (SRC / "ContosoSalesAI.SemanticModel").resolve()
