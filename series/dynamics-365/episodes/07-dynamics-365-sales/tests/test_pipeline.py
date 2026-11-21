import datetime as dt

from conftest import FakeResponse
from salesctl import cli, pipeline
from salesctl.pipeline import Deal

NOW = dt.date(2027, 1, 15)


def deals(rows):
    return [pipeline.to_deal(r) for r in rows]


def test_to_deal_reads_formatted_customer_and_category(rows):
    d = deals(rows)[0]
    assert d.customer == "Contoso Retail" and d.category_label == "Best case"
    assert d.close == dt.date(2027, 2, 10) and d.weighted == 72000


def test_weighted_treats_missing_probability_as_zero(rows):
    margie = [d for d in deals(rows) if d.name.startswith("Margie")][0]
    assert margie.probability is None and margie.weighted == 0


def test_summary_totals_and_buckets(rows):
    s = pipeline.summarize(deals(rows))
    assert s["count"] == 14 and s["value"] == 753500 and round(s["weighted"]) == 336075
    assert list(s["by_month"])[0] == "2026-12" and "no date" in s["by_month"]
    assert s["by_category"]["Committed"][0] == 4


def test_hygiene_finds_each_rule_once(rows):
    f = pipeline.hygiene(deals(rows), NOW)
    codes = [x.code for x in f]
    assert codes.count("H001") == 1 and codes.count("H002") == 1 and codes.count("H003") == 1
    assert codes.count("H004") == 1 and codes.count("H006") == 2
    assert [x.level for x in f][:3] == ["error"] * 3          # errors sort first


def test_hygiene_clean_deal_has_no_findings():
    d = Deal("1", "ok", "c", 1000, dt.date(2027, 3, 1), 50, 100000002, dt.date(2027, 1, 10))
    assert pipeline.hygiene([d], NOW) == []


def test_large_committed_deal_is_not_flagged():
    d = Deal("1", "big", "c", 90000, dt.date(2027, 1, 20), 90, 100000003, NOW)
    assert pipeline.hygiene([d], NOW) == []


def test_query_filters_open_and_owner():
    q = pipeline.query("00000000-0000-0000-0000-000000000001")
    assert "statecode eq 0" in q and "_ownerid_value eq 00000000-0000-0000-0000-000000000001" in q
    assert "estimatedvalue" in q and "msdyn_forecastcategory" in q


def test_fetch_open_pages_and_asks_for_annotations(api, stub, rows):
    nxt = "https://contoso-sales.crm4.dynamics.com/api/data/v9.2/opportunities?page=2"
    stub.on("GET", r"^opportunities\?\$select", FakeResponse(200, {"value": rows[:5], "@odata.nextLink": nxt}))
    stub.on("GET", r"page=2", FakeResponse(200, {"value": rows[5:]}))
    got = pipeline.fetch_open(api)
    assert len(got) == 14
    prefer = stub.requests[0]["headers"]["Prefer"]
    assert "odata.maxpagesize=500" in prefer and "FormattedValue" in prefer


def test_cli_pipeline_and_hygiene_offline(capsys):
    assert cli.main(["pipeline", "--from-json", str(__import__("conftest").SAMPLE), "--now", "2027-01-15"]) == 0
    out = capsys.readouterr().out
    assert "Open pipeline: 14 opportunities, 753,500 EUR, weighted 336,075 EUR" in out
    assert cli.main(["hygiene", "--from-json", str(__import__("conftest").SAMPLE), "--now", "2027-01-15"]) == 1
    assert "3 error(s), 6 warning(s)" in capsys.readouterr().out
