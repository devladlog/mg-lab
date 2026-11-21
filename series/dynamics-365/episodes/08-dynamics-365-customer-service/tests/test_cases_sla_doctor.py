import datetime as dt
import json

import pytest

from conftest import FakeResponse, SAMPLE, ROOT
from casekit import cases, cli, doctor, sla
from casekit.webapi import DataverseError

NOW = dt.datetime(2027, 1, 15, 12, 0, tzinfo=dt.timezone.utc)
CFG = cli.load_config()
CID = "00000000-0000-0000-0000-0000000000c1"


def load(rows):
    return [cases.to_case(r) for r in rows]


def test_to_case_reads_labels_and_flags(rows):
    c = load(rows)[0]
    assert c.number.startswith("CAS-") and c.customer == "Contoso Retail" and c.priority == 1
    assert c.first_response_sent is False and c.age_hours(NOW) == 4.5


def test_triage_rules_on_the_sample(rows):
    f = cases.triage(load(rows), NOW, CFG)
    codes = sorted(x.code for x in f)
    assert codes == ["C001", "C001", "C001", "C002", "C003", "C004"]
    assert f[0].level == "error" and f[-1].level == "info"


def test_first_response_not_flagged_before_target():
    c = cases.Case("1", "CAS-1", "t", "c", 2, NOW - dt.timedelta(hours=3), False, False, 1)
    assert cases.triage([c], NOW, CFG) == []


def test_on_hold_case_is_not_warned_as_due_soon():
    c = cases.Case("1", "CAS-1", "t", "c", 2, NOW - dt.timedelta(hours=60), True, False, 2)
    assert cases.triage([c], NOW, CFG) == []


def test_summary_counts(rows):
    lines = cases.summary(load(rows), NOW)
    assert lines[0] == "10 open case(s)" and any(l.startswith("High") and l.rstrip().endswith("1") for l in lines)


def test_fetch_open_filters_active_and_asks_for_labels(api, stub, rows):
    stub.on("GET", r"^incidents\?", FakeResponse(200, {"value": rows}))
    got = cases.fetch_open(api)
    assert len(got) == 10
    r = stub.requests[0]
    assert "statecode eq 0" in r["url"] and "FormattedValue" in r["headers"]["Prefer"]


def test_case_body_binding_and_validation():
    b = cases.case_body("t", "acc-1", priority=1, origin=1, case_type=2, description="d")
    assert b["customerid_account@odata.bind"] == "/accounts(acc-1)" and b["prioritycode"] == 1
    with pytest.raises(ValueError):
        cases.case_body("x" * 201, "a")
    with pytest.raises(ValueError):
        cases.case_body("t", "a", priority=9)


def test_seed_creates_only_missing_cases(api, stub):
    specs = json.loads((ROOT / "sample" / "demo-cases.json").read_text())
    stub.on("GET", r"^accounts\?", FakeResponse(200, {"value": [{"accountid": "acc-1"}]}))
    stub.on("GET", r"^incidents\?", FakeResponse(200, {"value": []}))
    stub.on("GET", r"Cannot sign in", FakeResponse(200, {"value": [{"incidentid": "x"}]}))
    stub.on("POST", r"^incidents$", FakeResponse(204))
    lines = []
    assert cases.seed(api, specs, CFG, apply=True, out=lines.append) == 4
    assert len(stub.sent("POST", "incidents")) == 4 and any(l.startswith("=") for l in lines)
    assert all(r["json"]["title"].startswith("[MGL demo] ") for r in stub.sent("POST"))


def test_seed_dry_run_and_missing_account(api, stub):
    stub.on("GET", r"^accounts\?", FakeResponse(200, {"value": []}))
    with pytest.raises(ValueError, match="episode 7"):
        cases.seed(api, [{"title": "a"}], CFG)
    stub.on("GET", r"^accounts\?", FakeResponse(200, {"value": [{"accountid": "acc-1"}]}))
    stub.on("GET", r"^incidents\?", FakeResponse(200, {"value": []}))
    cases.seed(api, [{"title": "a"}], CFG, out=lambda *_: None)
    assert stub.sent("POST") == []


def test_resolve_body_status_rules():
    b = cases.resolve_body(CID, "Fixed", "details")
    assert b["Status"] == 5 and b["IncidentResolution"]["incidentid@odata.bind"] == f"/incidents({CID})"
    assert b["IncidentResolution"]["@odata.type"] == "Microsoft.Dynamics.CRM.incidentresolution"
    assert cases.resolve_body(CID, "Info", status=1000)["Status"] == 1000
    with pytest.raises(ValueError):
        cases.resolve_body(CID, "x", status=6)


def test_resolve_apply_posts_closeincident_and_reads_back(api, stub):
    seq = iter([FakeResponse(200, {"ticketnumber": "CAS-1", "title": "t", "statecode": 0}),
                FakeResponse(200, {"statecode": 1, "statuscode": 5})])
    stub.on("GET", r"^incidents\(", lambda req: next(seq))
    stub.on("POST", r"^CloseIncident$", FakeResponse(204))
    lines = []
    res = cases.resolve(api, CID, apply=True, out=lines.append)
    assert res["statecode"] == 1 and "statecode 1 statuscode 5" in lines[-1]


def test_resolve_dry_run_and_closed_case(api, stub):
    stub.on("GET", r"^incidents\(", FakeResponse(200, {"ticketnumber": "CAS-1", "title": "t", "statecode": 0}))
    cases.resolve(api, CID, out=lambda *_: None)
    assert stub.sent("POST") == []
    stub.on("GET", r"^incidents\(", FakeResponse(200, {"ticketnumber": "CAS-1", "title": "t", "statecode": 1}))
    with pytest.raises(ValueError, match="not active"):
        cases.resolve(api, CID, apply=True)


KPI_ROWS = [
    {"ticketnumber": "CAS-1", "title": "a", "firstresponsebykpiid": {"status": 4},
     "resolvebykpiid": {"status": 2}},
    {"ticketnumber": "CAS-2", "title": "b", "firstresponsebykpiid": None, "resolvebykpiid": {"status": 1}},
]


def test_sla_query_expands_both_kpi_lookups():
    q = sla.query()
    assert "$expand=firstresponsebykpiid($select=status,warningtime,failuretime,succeededon)," in q
    assert "resolvebykpiid(" in q and "statecode eq 0" in q


def test_sla_report_labels_and_counts():
    lines = sla.report(KPI_ROWS)
    assert "Succeeded" in lines[1] and "Nearing Noncompliance" in lines[1]
    assert "no SLA applied" in lines[2] and "Noncompliant" in lines[2]
    assert lines[-1] == "2 open case(s), 2 KPI(s) noncompliant or nearing noncompliance"


def test_sla_rows_hint_when_expand_is_refused(api, stub):
    stub.on("GET", r"^incidents\?", FakeResponse(400, {"error": {"code": "0x0", "message": "Could not find a property"}}))
    with pytest.raises(DataverseError, match="casekit doctor"):
        sla.rows(api)


CSDL = """<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0"><edmx:DataServices>
<Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Microsoft.Dynamics.CRM">
<EntityType Name="incident"><NavigationProperty Name="resolvebykpiid" Type="mscrm.slakpiinstance"/>
  <NavigationProperty Name="firstresponsebykpiid" Type="mscrm.slakpiinstance"/>
  <NavigationProperty Name="customerid_account" Type="mscrm.account"/></EntityType>
<EntityType Name="incidentresolution"/><EntityType Name="sla"/>
<Action Name="CloseIncident"><Parameter Name="IncidentResolution" Type="mscrm.crmbaseentity"/>
  <Parameter Name="Status" Type="Edm.Int32"/></Action>
</Schema></edmx:DataServices></edmx:Edmx>"""


def test_doctor_parse_and_report(api, stub):
    info = doctor.parse(CSDL)
    assert info["kpi_lookups"] == ["firstresponsebykpiid", "resolvebykpiid"]
    assert info["close"] == {"bound": False, "params": [("IncidentResolution", "mscrm.crmbaseentity"),
                                                         ("Status", "Edm.Int32")]}
    stub.on("GET", r"^\$metadata$", FakeResponse(200, None, text=CSDL))
    lines = []
    assert doctor.check(api, out=lines.append) == 0
    assert any("slakpiinstance" in l and "MISSING" in l for l in lines) and lines[-1] == "OK"


def test_doctor_without_customer_service_fails(api, stub):
    stub.on("GET", r"^\$metadata$", FakeResponse(200, None, text=CSDL.replace("CloseIncident", "Other")
                                                  .replace('<EntityType Name="incidentresolution"/>', "")))
    lines = []
    assert doctor.check(api, out=lines.append) == 1
    assert any("CloseIncident" in l and "MISSING" in l for l in lines)


def test_cli_triage_offline(capsys):
    assert cli.main(["triage", "--from-json", str(SAMPLE), "--now", "2027-01-15T12:00:00Z"]) == 1
    out = capsys.readouterr().out
    assert "10 open case(s)" in out and "4 error(s), 1 warning(s)" in out
