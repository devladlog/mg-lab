"""The PBIP, the TMDL model and the empty report: static checks only. Nothing here opens Power BI Desktop and no DAX engine runs."""
import json
import re

import pytest

import events
from conftest import MODEL, SRC, schema_errors

TABLE = (MODEL / "tables" / "Till Events.tmdl").read_text(encoding="utf-8")


def test_the_table_is_directquery_over_the_deduplicated_view():
    assert "\t\tmode: directQuery" in TABLE
    assert 'AzureDataExplorer.Contents(KqlClusterUri, KqlDatabase, "TillEventsUnique", [])' in TABLE


def test_columns_match_the_event_fields_in_order():
    assert re.findall(r"^\t\tsourceColumn: (\w+)$", TABLE, flags=re.M) == events.FIELDS
    assert re.findall(r"^\tcolumn (\w+)$", TABLE, flags=re.M) == events.FIELDS


def test_column_types_follow_the_kql_types():
    want = {"EventTime": "dateTime", "Quantity": "int64", "UnitPrice": "double", "Amount": "double"}
    for name in events.FIELDS:
        block = re.search(rf"^\tcolumn {name}\n((?:\t\t.*\n)+)", TABLE, flags=re.M).group(1)
        assert f"dataType: {want.get(name, 'string')}" in block, name


def test_measures_reference_existing_columns_only():
    cols = set(events.FIELDS)
    for m in re.finditer(r"'Till Events'\[(\w+)\]", TABLE.split("\tcolumn ")[0]):
        assert m.group(1) in cols
    measures = re.findall(r"^\tmeasure ('[^']+'|\w+) =", TABLE, flags=re.M)
    assert measures == ["'Sales Amount'", "Orders", "Units", "'Last Event Time'"]


def test_parameters_hold_placeholders_not_real_addresses():
    ex = (MODEL / "expressions.tmdl").read_text(encoding="utf-8")
    assert "contoso-lab" in ex and "devladlog" not in ex.lower()
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ex)


def test_model_references_the_table():
    assert "ref table 'Till Events'" in (MODEL / "model.tmdl").read_text(encoding="utf-8")


def test_tmdl_uses_tabs_only():
    for f in MODEL.rglob("*.tmdl"):
        for line in f.read_text(encoding="utf-8").split("\n"):
            assert not line.startswith(" "), (f.name, line)


@pytest.mark.parametrize("path", [SRC / "ContosoLive.pbip", SRC / "ContosoLive.SemanticModel/definition.pbism",
                                  SRC / "ContosoLive.Report/definition.pbir", *sorted((SRC / "ContosoLive.Report").rglob("*.json"))],
                         ids=lambda p: str(p.relative_to(SRC)))
def test_project_files_match_their_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_pbip_points_at_the_report_and_the_report_at_the_model():
    pbip = json.loads((SRC / "ContosoLive.pbip").read_text(encoding="utf-8"))
    assert pbip["artifacts"][0]["report"]["path"] == "ContosoLive.Report"
    pbir = json.loads((SRC / "ContosoLive.Report/definition.pbir").read_text(encoding="utf-8"))
    assert (SRC / "ContosoLive.Report" / pbir["datasetReference"]["byPath"]["path"]).resolve() == (SRC / "ContosoLive.SemanticModel").resolve()
