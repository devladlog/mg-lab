import json

import pytest

from reportkit import charts
from reportkit.cli import main
from conftest import ENV, FakeResponse


@pytest.mark.parametrize("name", sorted(charts.BUILDERS))
def test_builtin_charts_validate(name):
    assert charts.validate(charts.BUILDERS[name]()) == []


def test_multi_series_needs_matching_series():
    spec = charts.estimated_vs_actual_by_month()
    spec["presentation"] = spec["presentation"].replace(charts._series("Column", "237, 125, 49", False), "")
    problems = charts.validate(spec)
    assert any("1 <Series>" in p and "2 <measurecollection>" in p for p in problems)


def test_measure_must_exist_in_fetch():
    spec = charts.pipeline_by_category()
    spec["data"] = spec["data"].replace('<measure alias="sum_estimatedvalue" />', '<measure alias="nope" />')
    assert any("'nope'" in p for p in charts.validate(spec))


def test_aggregate_flag_and_groupby_required():
    spec = charts.pipeline_by_category()
    spec["data"] = spec["data"].replace('aggregate="true">', '>', 1)
    assert any("aggregate" in p for p in charts.validate(spec))
    spec = charts.pipeline_by_category()
    spec["data"] = spec["data"].replace('groupby="true"', '')
    assert any("groupby" in p for p in charts.validate(spec))


def test_malformed_xml_and_long_name():
    spec = charts.pipeline_by_category()
    spec["data"] = "<datadefinition>"
    assert "not well-formed" in charts.validate(spec)[0]
    spec = charts.pipeline_by_category()
    spec["name"] = "x" * 95
    assert any("allows 100" in p for p in charts.validate(spec))


def test_body_matches_documented_columns():
    b = charts.body(charts.pipeline_by_category())
    assert set(b) == {"name", "primaryentitytypecode", "charttype", "isdefault", "description",
                      "datadescription", "presentationdescription"}
    assert b["name"].startswith("[MGL demo] ") and b["primaryentitytypecode"] == "opportunity" and b["charttype"] == 0


def test_create_dry_run_apply_and_existing(api, stub):
    stub.on("GET", r"userqueryvisualizations\?\$select", FakeResponse(200, {"value": []}))
    out = []
    charts.create(api, charts.pipeline_by_category(), apply=False, out=out.append)
    assert out[0].endswith("(dry run)") and not stub.sent("POST")
    stub.on("POST", r"^userqueryvisualizations$", FakeResponse(204, headers={
        "OData-EntityId": ENV + "/api/data/v9.2/userqueryvisualizations(00000000-0000-0000-0000-0000000000c1)"}))
    cid = charts.create(api, charts.pipeline_by_category(), apply=True, out=out.append)
    assert cid == "00000000-0000-0000-0000-0000000000c1" and len(stub.sent("POST")) == 1
    stub.on("GET", r"userqueryvisualizations\?\$select", FakeResponse(200, {"value": [
        {"userqueryvisualizationid": "00000000-0000-0000-0000-0000000000c2"}]}))
    assert charts.create(api, charts.pipeline_by_category(), apply=True, out=out.append) == \
        "00000000-0000-0000-0000-0000000000c2"
    assert len(stub.sent("POST")) == 1                   # not created twice


def test_invalid_chart_is_not_sent(api, stub):
    spec = charts.pipeline_by_category()
    spec["data"] = "<broken"
    with pytest.raises(ValueError, match="invalid"):
        charts.create(api, spec, apply=True)
    assert not stub.requests


def test_cli_chart_dry_run(monkeypatch, stub, capsys):
    from reportkit import cli
    from reportkit.webapi import WebApi
    stub.on("GET", r"userqueryvisualizations\?\$select", FakeResponse(200, {"value": []}))
    monkeypatch.setattr(cli, "make_api", lambda a: WebApi(ENV, lambda: "t", session=stub, sleep=lambda s: None))
    assert main(["chart", "pipeline"]) == 0
    assert "(dry run)" in capsys.readouterr().out and not stub.sent("POST")
