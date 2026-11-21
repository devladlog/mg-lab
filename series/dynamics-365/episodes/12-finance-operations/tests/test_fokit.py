import pytest

from fokit import cli, customers, reconcile
from fokit.fo import FoApi, FoError
from conftest import FO_ENV, FakeResponse, sample


# ---- OData client -------------------------------------------------------------------------------------------

def test_url_has_select_company_filter_and_cross_company(fo, cfg):
    url = customers.fo_url(fo, cfg, company="usmf")
    assert url.startswith(FO_ENV + "/data/CustomersV3?$select=CustomerAccount,dataAreaId,OrganizationName")
    assert "$filter=dataAreaId%20eq%20'usmf'" in url and url.endswith("cross-company=true")


def test_company_name_with_a_quote_is_escaped(fo, cfg):
    assert "'a''b'" in customers.fo_url(fo, cfg, company="a'b").replace("%20", " ")


def test_every_call_sends_the_bearer_token(fo, stub, cfg):
    stub.on(r"/data/CustomersV3", FakeResponse(200, {"value": []}))
    list(fo.get_all(customers.fo_url(fo, cfg)))
    assert stub.requests[0]["headers"]["Authorization"] == "Bearer test-token"


def test_paging_follows_next_link_until_it_is_gone(fo, stub, cfg):
    p2 = FO_ENV + "/data/CustomersV3?$skiptoken=2"
    stub.on(r"/data/CustomersV3\?\$select", FakeResponse(200, {"value": [{"CustomerAccount": "A"}], "@odata.nextLink": p2}))
    stub.on(r"skiptoken=2", FakeResponse(200, {"value": [{"CustomerAccount": "B"}]}))
    assert [r["CustomerAccount"] for r in fo.get_all(customers.fo_url(fo, cfg))] == ["A", "B"]
    assert len(stub.requests) == 2


def test_429_waits_for_retry_after_then_succeeds(stub, cfg):
    waits = []
    api = FoApi(FO_ENV, lambda: "t", session=stub, sleep=waits.append)
    answers = iter([FakeResponse(429, {"error": {"message": "Too many requests"}}, {"Retry-After": "7"}),
                    FakeResponse(200, {"value": [{"CustomerAccount": "A"}]})])
    stub.on(r"/data/", lambda req: next(answers))
    assert len(list(api.get_all(api.url("CustomersV3")))) == 1
    assert waits == [7.0]


def test_429_forever_gives_up_with_the_status(stub):
    api = FoApi(FO_ENV, lambda: "t", session=stub, max_retries=2, sleep=lambda s: None)
    stub.on(r"/data/", FakeResponse(429, {"error": {"message": "busy"}}, {"Retry-After": "1"}))
    with pytest.raises(FoError) as e:
        list(api.get_all(api.url("CustomersV3")))
    assert e.value.status == 429 and len(stub.requests) == 3


def test_error_message_and_non_json_error_bodies(fo, stub):
    stub.on(r"/data/Bad", FakeResponse(401, {"error": {"message": "AADSTS: app not registered"}}))
    stub.on(r"/data/Html", FakeResponse(502, text="<html>bad gateway</html>"))
    with pytest.raises(FoError, match="app not registered"):
        list(fo.get_all(fo.url("Bad")))
    with pytest.raises(FoError, match="bad gateway"):
        list(fo.get_all(fo.url("Html")))


# ---- reading customers and accounts --------------------------------------------------------------------------

def test_fetch_customers_normalizes_rows(fo, stub, cfg):
    stub.on(r"/data/CustomersV3", FakeResponse(200, {"value": sample("fo-customers.json")}))
    data = customers.fetch_customers(fo, cfg)
    assert len(data) == 7 and data[0] == customers.FoCustomer("C-1001", "demf", "Contoso Retail", "Organization", "10")


def test_dataverse_query_and_paging(dv, stub, cfg):
    nxt = "https://contoso-lab.crm4.dynamics.com/api/data/v9.2/accounts?$skiptoken=x"
    stub.on(r"accounts\?\$select", FakeResponse(200, {"value": [{"accountnumber": "C-1", "name": "A"}], "@odata.nextLink": nxt}))
    stub.on(r"skiptoken=x", FakeResponse(200, {"value": [{"accountnumber": " C-2 ", "name": "B"}]}))
    got = customers.fetch_accounts(dv, cfg)
    assert [a.number for a in got] == ["C-1", "C-2"]
    assert "accountnumber ne null" in stub.requests[0]["url"]
    assert "odata.maxpagesize=500" in stub.requests[0]["headers"]["Prefer"]


# ---- reconcile ----------------------------------------------------------------------------------------------

def sample_findings():
    fo = [customers.to_customer(r) for r in sample("fo-customers.json")]
    dv = [customers.to_account(r) for r in sample("dv-accounts.json")]
    return {(f.rule, f.subject): f for f in reconcile.reconcile(fo, dv)}


def test_sample_findings():
    f = sample_findings()
    assert set(f) == {("R004", "C-1001"), ("R003", "C-1004"), ("R001", "C-3001"), ("R002", "C-1099"), ("R005", "Person")}
    assert f[("R001", "C-3001")].level == "error" and f[("R005", "Person")].level == "info"


def test_names_that_differ_only_in_case_or_spacing_match():
    assert reconcile.norm("Contoso  Hospitality Group ") == reconcile.norm("CONTOSO hospitality group")
    assert ("R003", "C-1003") not in sample_findings()


def test_clean_data_has_no_findings():
    fo = [customers.FoCustomer("A", "demf", "Alpha", "Organization", "10")]
    assert reconcile.reconcile(fo, [customers.DvAccount("A", "alpha")]) == []


def test_people_are_not_matched_against_accounts():
    fo = [customers.FoCustomer("P1", "demf", "Alex Demo", "Person", "10")]
    assert [f.rule for f in reconcile.reconcile(fo, [])] == ["R005"]


# ---- CLI ----------------------------------------------------------------------------------------------------

def test_cli_reconcile_offline_exit_code_and_output(capsys):
    root = cli.EPISODE / "sample"
    code = cli.main(["reconcile", "--fo-json", str(root / "fo-customers.json"), "--dv-json", str(root / "dv-accounts.json")])
    out = capsys.readouterr().out
    assert code == 1 and "ERROR   R001  C-3001" in out and "1 error(s), 3 warning(s), 1 info" in out


def test_cli_customers_offline_lists_companies(capsys):
    assert cli.main(["customers", "--fo-json", str(cli.EPISODE / "sample" / "fo-customers.json"), "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert "7 customer(s)" in out and "demf     5" in out and "dem2     2" in out


def test_cli_asks_for_the_environment_url(monkeypatch):
    monkeypatch.delenv("FO_URL", raising=False)
    with pytest.raises(SystemExit, match="FO_URL"):
        cli.main(["doctor"])


def test_cli_company_filter_also_applies_to_offline_data(capsys):
    assert cli.main(["customers", "--fo-json", str(cli.EPISODE / "sample" / "fo-customers.json"), "--company", "dem2"]) == 0
    assert "2 customer(s)" in capsys.readouterr().out
