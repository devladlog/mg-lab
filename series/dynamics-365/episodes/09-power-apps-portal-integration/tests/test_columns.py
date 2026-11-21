from pagekit import columns
from pagekit.cli import main
from conftest import ENV, GOOD, FakeResponse, not_found

INCIDENT = ["title", "description", "prioritycode", "createdon", "statecode", "ticketnumber", "customerid"]
CONTACT = ["firstname", "lastname", "emailaddress1"]


def attrs(names):
    return FakeResponse(200, {"value": [{"LogicalName": n} for n in names]})


def test_all_columns_exist(stub, api, good_site):
    stub.on("GET", r"EntityDefinitions\(LogicalName='incident'\)/Attributes", attrs(INCIDENT))
    stub.on("GET", r"EntityDefinitions\(LogicalName='contact'\)/Attributes", attrs(CONTACT))
    assert columns.check(api, good_site) == []


def test_misspelt_column_is_found(stub, api, good_site):
    stub.on("GET", r"LogicalName='incident'", attrs([c for c in INCIDENT if c != "prioritycode"] + ["priority"]))
    stub.on("GET", r"LogicalName='contact'", attrs(CONTACT))
    f = columns.check(api, good_site)
    assert [(x.code, x.where) for x in f] == [("F001", "Webapi/incident")]
    assert "prioritycode" in f[0].message


def test_metadata_error_is_a_finding(stub, api, good_site):
    stub.on("GET", r"LogicalName='contact'", attrs(CONTACT))
    f = columns.check(api, good_site)           # no route for incident: 404 from the stub
    assert [(x.code, x.where) for x in f] == [("F002", "Webapi/incident")]


def test_wildcard_and_disabled_tables_are_skipped(stub, api, bad_site):
    stub.on("GET", r"LogicalName='", attrs(["name"]))
    where = {x.where for x in columns.check(api, bad_site)}
    assert "Webapi/incident" not in where and "Webapi/lead" not in where


def test_cli_columns(monkeypatch, stub, capsys):
    from pagekit import cli
    from pagekit.webapi import WebApi
    stub.on("GET", r"LogicalName='incident'", attrs(INCIDENT))
    stub.on("GET", r"LogicalName='contact'", attrs(CONTACT))
    monkeypatch.setattr(cli, "make_api", lambda a: WebApi(ENV, lambda: "t", session=stub, sleep=lambda s: None))
    assert main(["columns", str(GOOD)]) == 0
    assert "0 error(s)" in capsys.readouterr().out
