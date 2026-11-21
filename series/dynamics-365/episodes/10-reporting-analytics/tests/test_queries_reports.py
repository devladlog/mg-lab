import json
import xml.etree.ElementTree as ET

import pytest

from reportkit import queries as Q, reports
from reportkit.cli import main
from reportkit.webapi import DataverseError
from conftest import ENV, FakeResponse, SAMPLE, apply_response, fetch_response


def test_fetchxml_is_wellformed_and_follows_learn_rules():
    for xml in (Q.fetch_by_column(), Q.fetch_by_month()):
        root = ET.fromstring(xml)
        assert root.get("aggregate") == "true"
        groups = [a for a in root.iter("attribute") if a.get("groupby") == "true"]
        orders = {o.get("alias") for o in root.iter("order")}
        assert groups and all(a.get("alias") in orders for a in groups)       # grouping needs an order on the alias
    month = [a for a in ET.fromstring(Q.fetch_by_month()).iter("attribute") if a.get("dategrouping")]
    assert {a.get("dategrouping") for a in month} == {"year", "month"}
    assert all(a.get("usertimezone") == "false" for a in month)


def test_apply_query_text():
    assert Q.apply_by_column() == ("opportunities?$apply=filter(statecode eq 0)/groupby((msdyn_forecastcategory),"
                                   "aggregate(estimatedvalue with sum as total,$count as n))")


def test_three_ways_agree_on_the_sample(api, env, rows):
    res = reports.category_three_ways(api, "msdyn_forecastcategory")
    out = []
    assert reports.reconcile(res, out.append) == 0
    assert out[0].startswith("OK") and out[1].startswith("OK")
    assert sum(g.total for g in res["FetchXML aggregate"].values()) == 753500
    assert res["client-side rows"][100000001].count == 7


def test_mismatch_is_reported(api, env, rows):
    wrong = apply_response(rows)
    wrong["value"][0]["total"] += 1000
    env.on("GET", r"^opportunities\?\$apply=", FakeResponse(200, wrong))
    out = []
    assert reports.reconcile(reports.category_three_ways(api, "msdyn_forecastcategory"), out.append) == 1
    assert any(l.startswith("MISMATCH OData $apply") for l in out)
    assert any("100000001" in l for l in out)


def test_missing_group_is_reported(api, env, rows):
    short = apply_response(rows)
    short["value"].pop()
    env.on("GET", r"^opportunities\?\$apply=", FakeResponse(200, short))
    out = []
    assert reports.reconcile(reports.category_three_ways(api, "msdyn_forecastcategory"), out.append) == 1
    assert any("only in reference" in l for l in out)


def test_month_grouping_with_null_date(api, env, rows):
    res = reports.month_two_ways(api)
    assert reports.reconcile(res, lambda s: None) == 0
    assert None in res["FetchXML aggregate"] and res["FetchXML aggregate"][None].total == 41000
    assert res["client-side rows"][(2027, 1)].count == 6


def test_money_null_group_total_is_zero():
    rep = Q.from_fetch_rows([{"grp": 1, "n": 2}])
    assert rep[1].total == 0.0 and rep[1].count == 2


def test_aggregate_limit_is_explained(api, stub):
    err = {"error": {"code": "0x8004E023", "message": "AggregateQueryRecordLimit exceeded. Cannot perform this operation."}}
    stub.on("GET", r"fetchXml", FakeResponse(400, err))
    with pytest.raises(Q.AggregateLimit, match="50,000"):
        Q.run_fetch(api, Q.fetch_by_column())


def test_other_errors_pass_through(api, stub):
    stub.on("GET", r"fetchXml", FakeResponse(403, {"error": {"code": "0x1", "message": "denied"}}))
    with pytest.raises(DataverseError):
        Q.run_fetch(api, Q.fetch_by_column())


def test_fetch_is_url_encoded_and_asks_for_annotations(api, env):
    Q.run_fetch(api, Q.fetch_by_column())
    req = env.sent("GET", "fetchXml")[0]
    assert "%3Cfetch" not in req["url"]                  # the stub decodes the URL; the raw one was encoded
    assert "FormattedValue" in req["headers"]["Prefer"]


def test_csv(tmp_path, rows):
    rep = Q.from_client_rows(rows, "msdyn_forecastcategory")
    p = tmp_path / "x.csv"
    reports.write_csv(rep, p)
    lines = p.read_text().splitlines()
    assert lines[0] == "group,open,estimated_value" and "Pipeline,7,435000.00" in lines


def test_cli_offline_and_queries(capsys, tmp_path):
    assert main(["pipeline", "--from-json", str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "Pipeline" in out and "753,500.00" in out and "no environment" in out
    assert main(["monthly", "--from-json", str(SAMPLE)]) == 0
    assert "(none)" in capsys.readouterr().out
    assert main(["queries"]) == 0
    assert "$apply" in capsys.readouterr().out


def test_cli_reconcile_exit_codes(monkeypatch, env, rows, capsys):
    from reportkit import cli
    from reportkit.webapi import WebApi
    monkeypatch.setattr(cli, "make_api", lambda a: WebApi(ENV, lambda: "t", session=env, sleep=lambda s: None))
    assert main(["reconcile"]) == 0
    capsys.readouterr()
    env.on("GET", r"^opportunities\?fetchXml=.*msdyn_forecastcategory", FakeResponse(200, {"value": []}))
    assert main(["reconcile"]) == 1
