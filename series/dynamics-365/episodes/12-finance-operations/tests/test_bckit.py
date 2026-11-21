import base64

import pytest
import requests

from bckit import cli, customers, reconcile
from bckit.bc import BcApi, BcError, odata_string
from conftest import BC_BASE, COMPANY_ID, COMPANY_ID2, ROOT_URL, FakeResponse, sample, two_companies


# ---- API client ---------------------------------------------------------------------------------------------

def test_url_has_company_select_filter_orderby_top(bc):
    url = bc.url(COMPANY_ID, "salesInvoices", select=["number", "status"], filter="status eq 'Open'",
                 orderby="invoiceDate desc", top=5)
    assert url.startswith(f"{ROOT_URL}/companies({COMPANY_ID})/salesInvoices?$select=number,status")
    assert "$filter=status%20eq%20'Open'" in url and "$orderby=invoiceDate%20desc" in url and url.endswith("$top=5")


def test_a_quote_in_a_value_is_escaped():
    assert odata_string("O'Brien Ltd") == "'O''Brien Ltd'"


def test_every_call_sends_basic_auth_and_the_page_size(bc, stub):
    stub.on(r"/customers", FakeResponse(200, {"value": []}))
    list(bc.get_all(bc.url(COMPANY_ID, "customers"), page_size=300))
    h = stub.requests[0]["headers"]
    assert h["Authorization"] == "Basic " + base64.b64encode(b"admin:not-a-real-password").decode()
    assert h["Prefer"] == "odata.maxpagesize=300"


def test_paging_follows_next_link_until_it_is_gone(bc, stub):
    p2 = ROOT_URL + f"/companies({COMPANY_ID})/customers?$skiptoken=2"
    stub.on(r"customers\?\$select", FakeResponse(200, {"value": [{"number": "A"}], "@odata.nextLink": p2}))
    stub.on(r"skiptoken=2", FakeResponse(200, {"value": [{"number": "B"}]}))
    assert [r["number"] for r in bc.get_all(bc.url(COMPANY_ID, "customers", select=["number"]))] == ["A", "B"]
    assert len(stub.requests) == 2


def test_a_next_link_that_repeats_stops_instead_of_looping(bc, stub):
    loop = ROOT_URL + "/companies?$skiptoken=1"
    stub.on(r"companies", FakeResponse(200, {"value": [{"id": "x"}], "@odata.nextLink": loop}))
    with pytest.raises(BcError, match="repeated"):
        list(bc.get_all(bc.companies_url()))


def test_429_waits_for_retry_after_then_succeeds(stub):
    waits = []
    api = BcApi(BC_BASE, "u", "p", session=stub, sleep=waits.append)
    answers = iter([FakeResponse(429, {"error": {"code": "x", "message": "Too many requests"}}, {"Retry-After": "7"}),
                    FakeResponse(200, {"value": [{"id": "1"}]})])
    stub.on(r"GET .*/companies", lambda req: next(answers))
    assert len(list(api.get_all(api.companies_url()))) == 1
    assert waits == [7.0]


def test_503_is_retried_for_reads_with_backoff_when_there_is_no_retry_after(stub):
    waits = []
    api = BcApi(BC_BASE, "u", "p", session=stub, sleep=waits.append)
    answers = iter([FakeResponse(503, text="queue timeout"), FakeResponse(503, text="queue timeout"),
                    FakeResponse(200, {"value": []})])
    stub.on(r"GET .*/companies", lambda req: next(answers))
    list(api.get_all(api.companies_url()))
    assert waits == [1.0, 2.0]


def test_a_post_is_never_retried_on_503(bc, stub):
    stub.on(r"POST ", FakeResponse(503, text="busy"))
    with pytest.raises(BcError) as e:
        bc.request("POST", bc.url(COMPANY_ID, "customers"), body={"displayName": "x"})
    assert e.value.status == 503 and len(stub.requests) == 1


def test_429_forever_gives_up_with_the_status(stub):
    api = BcApi(BC_BASE, "u", "p", session=stub, max_retries=2, sleep=lambda s: None)
    stub.on(r"GET ", FakeResponse(429, {"error": {"message": "busy"}}, {"Retry-After": "1"}))
    with pytest.raises(BcError) as e:
        list(api.get_all(api.companies_url()))
    assert e.value.status == 429 and len(stub.requests) == 3


def test_error_body_code_hint_and_non_json_body(bc, stub):
    stub.on(r"/Bad", FakeResponse(401, {"error": {"code": "Unauthorized", "message": "The credentials are not valid"}}))
    stub.on(r"/Html", FakeResponse(502, text="<html>bad gateway</html>"))
    stub.on(r"/Off", FakeResponse(405, text=""))
    with pytest.raises(BcError, match="credentials are not valid.*BC_PASSWORD") as e:
        bc.request("GET", ROOT_URL + "/Bad")
    assert e.value.code == "Unauthorized"
    with pytest.raises(BcError, match="bad gateway"):
        bc.request("GET", ROOT_URL + "/Html")
    with pytest.raises(BcError, match="405.*switched off"):
        bc.request("GET", ROOT_URL + "/Off")


def test_unreachable_container_gives_a_readable_error(bc, stub):
    stub.on(r"GET ", requests.exceptions.ConnectionError("refused"))
    with pytest.raises(BcError, match="cannot reach.*docker ps"):
        bc.request("GET", bc.companies_url())


def test_204_has_no_body(bc, stub):
    stub.on(r"DELETE ", FakeResponse(204))
    assert bc.request("DELETE", ROOT_URL + "/x") is None


# ---- reading customers, invoices, accounts ------------------------------------------------------------------

def sample_bc(stub):
    two_companies(stub)
    data = {c["name"]: c["customers"] for c in sample("bc-customers.json")["companies"]}
    stub.on(rf"companies\({COMPANY_ID}\)/customers", FakeResponse(200, {"value": data["CRONUS USA, Inc."]}))
    stub.on(rf"companies\({COMPANY_ID2}\)/customers", FakeResponse(200, {"value": data["Contoso Test Co"]}))


def test_fetch_customers_walks_every_company(bc, stub, cfg):
    sample_bc(stub)
    got = customers.fetch_customers(bc, cfg)
    assert len(got) == 6 and got[0] == customers.BcCustomer("10000", "CRONUS USA, Inc.", "Contoso Retail", "Company", "USD", "")
    assert got[-1].company == "Contoso Test Co" and got[3].blocked == "Invoice"
    assert "$select=number,displayName,type,currencyCode,blocked" in stub.requests[1]["url"]


def test_one_company_by_name_and_an_unknown_name_lists_the_real_ones(bc, stub, cfg):
    sample_bc(stub)
    assert {c.company for c in customers.fetch_customers(bc, cfg, "contoso test co")} == {"Contoso Test Co"}
    with pytest.raises(BcError, match="no company named 'Nope'.*CRONUS USA, Inc."):
        customers.fetch_customers(bc, cfg, "Nope")


def test_invoices_filter_status_and_customer_and_remaining(bc, stub, cfg):
    two_companies(stub)
    stub.on(rf"companies\({COMPANY_ID}\)/salesInvoices", FakeResponse(200, {"value": [
        {"number": "103001", "customerNumber": "10000", "customerName": "Contoso Retail", "invoiceDate": "2026-11-01",
         "dueDate": "2026-12-01", "status": "Open", "currencyCode": "USD", "totalAmountIncludingTax": 1250.5,
         "remainingAmount": 1250.5}]}))
    got = customers.fetch_invoices(bc, cfg, "CRONUS USA, Inc.", status="Open", customer="10000", top=5)
    assert got == [customers.BcInvoice("103001", "CRONUS USA, Inc.", "10000", "Contoso Retail", "2026-11-01", "2026-12-01",
                                       "Open", "USD", 1250.5, 1250.5)]
    url = stub.requests[1]["url"]
    assert "$filter=status eq 'Open' and customerNumber eq '10000'" in url and "$orderby=invoiceDate desc" in url


def test_seed_creates_missing_customers_and_skips_existing(bc, stub, cfg):
    two_companies(stub)
    stub.on(rf"GET .*companies\({COMPANY_ID}\)/customers", FakeResponse(200, {"value": []}))
    stub.on(r"GET .*displayName eq 'Contoso Retail'", FakeResponse(200, {"value": [{"number": "10000", "displayName": "Contoso Retail"}]}))
    stub.on(rf"POST .*companies\({COMPANY_ID}\)/customers", lambda req: FakeResponse(201, {"number": "60000", **req["json"]}))
    log = customers.seed_customers(bc, cfg, "CRONUS USA, Inc.")
    assert log[0] == "exists   10000      Contoso Retail"
    assert log[1].startswith("created  60000") and len(log) == 4
    posts = [r["json"] for r in stub.requests if r["method"] == "POST"]
    assert len(posts) == 3 and posts[-1] == {"displayName": "Alex Demo", "type": "Person"}


def test_seed_dry_run_writes_nothing(bc, stub, cfg):
    two_companies(stub)
    stub.on(r"GET .*/customers", FakeResponse(200, {"value": []}))
    log = customers.seed_customers(bc, cfg, "CRONUS USA, Inc.", dry_run=True)
    assert log[0] == "would create Contoso Retail (Company)" and not [r for r in stub.requests if r["method"] == "POST"]


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
    bc = cli.read_bc_json(str(cli.EPISODE / "sample" / "bc-customers.json"))
    dv = [customers.to_account(r) for r in sample("dv-accounts.json")["value"]]
    return {(f.rule, f.subject): f for f in reconcile.reconcile(bc, dv)}


def test_sample_findings():
    f = sample_findings()
    assert set(f) == {("R004", "10000"), ("R001", "30000"), ("R003", "20000"), ("R006", "40000"), ("R002", "99000"),
                      ("R005", "Person")}
    assert f[("R001", "30000")].level == "error" and f[("R005", "Person")].level == "info"


def test_names_that_differ_only_in_case_or_spacing_match():
    assert reconcile.norm("Contoso  Retail ") == reconcile.norm("CONTOSO retail")
    assert ("R003", "10000") not in sample_findings()


def test_clean_data_has_no_findings():
    bc = [customers.BcCustomer("1", "C", "Alpha", "Company")]
    assert reconcile.reconcile(bc, [customers.DvAccount("1", "alpha")]) == []


def test_people_are_not_matched_against_accounts():
    bc = [customers.BcCustomer("P1", "C", "Alex Demo", "Person")]
    assert [f.rule for f in reconcile.reconcile(bc, [])] == ["R005"]


def test_a_customer_with_no_account_is_not_also_reported_as_blocked_or_renamed():
    bc = [customers.BcCustomer("1", "C", "Alpha", "Company", blocked="All")]
    assert [f.rule for f in reconcile.reconcile(bc, [])] == ["R001"]


# ---- CLI ----------------------------------------------------------------------------------------------------

BCJ = str(cli.EPISODE / "sample" / "bc-customers.json")
DVJ = str(cli.EPISODE / "sample" / "dv-accounts.json")


def test_cli_reconcile_offline_exit_code_and_output(capsys):
    code = cli.main(["reconcile", "--bc-json", BCJ, "--dv-json", DVJ])
    out = capsys.readouterr().out
    assert code == 1 and "ERROR   R001  30000" in out and "1 error(s), 3 warning(s), 2 info" in out
    assert "Business Central: 6 customer(s) in 2 company(ies)" in out


def test_cli_reconcile_name_scope_applies_to_both_sides(capsys):
    code = cli.main(["reconcile", "--bc-json", BCJ, "--dv-json", DVJ, "--name-contains", "logistics"])
    out = capsys.readouterr().out
    assert code == 0 and "scope: names containing 'logistics'" in out and "R003  20000" in out and "R001" not in out


def test_cli_customers_offline_lists_companies(capsys):
    assert cli.main(["customers", "--bc-json", BCJ, "--limit", "2"]) == 0
    out = capsys.readouterr().out
    assert "6 customer(s)" in out and "CRONUS USA, Inc." in out and "Contoso Test Co" in out


def test_cli_company_filter_also_applies_to_offline_data(capsys):
    assert cli.main(["customers", "--bc-json", BCJ, "--company", "Contoso Test Co"]) == 0
    assert "1 customer(s)" in capsys.readouterr().out


def test_cli_asks_for_the_password_and_never_echoes_it(monkeypatch, capsys):
    monkeypatch.delenv("BC_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="BC_PASSWORD"):
        cli.main(["doctor"])


def test_cli_doctor_reports_a_failed_login_as_an_error_line(monkeypatch, capsys, stub):
    monkeypatch.setenv("BC_PASSWORD", "wrong")
    stub.on(r"GET ", FakeResponse(401, {"error": {"code": "Unauthorized", "message": "bad login"}}))
    monkeypatch.setattr(requests, "Session", lambda: stub)
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("GET http://mglab-bc:7048/BC/api/v2.0/") and "error: HTTP 401: bad login" in out and "wrong" not in out


def test_cli_doctor_lists_companies(monkeypatch, capsys, stub):
    monkeypatch.setenv("BC_PASSWORD", "x")
    stub.on(r"GET .*/api/v2\.0/$", FakeResponse(200, {"value": [{"name": "companies"}]}))
    two_companies(stub)
    monkeypatch.setattr(requests, "Session", lambda: stub)
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "2 company(ies): 'CRONUS USA, Inc.', 'Contoso Test Co'" in out


def test_cli_base_url_comes_from_env_or_option(monkeypatch, stub):
    monkeypatch.setenv("BC_PASSWORD", "x")
    monkeypatch.setenv("BC_BASE_URL", "https://example.invalid:7048/BC2/")
    args = cli.build_parser().parse_args(["companies"])
    assert cli.make_bc(args, cli.load_config()).root == "https://example.invalid:7048/BC2/api/v2.0"
    args = cli.build_parser().parse_args(["--bc-url", "http://other:7048/BC", "companies"])
    assert cli.make_bc(args, cli.load_config()).root == "http://other:7048/BC/api/v2.0"
