import datetime as dt

import pytest

from conftest import FakeResponse, not_found
from salesctl import close, doctor, lead
from salesctl.webapi import DataverseError

LID = "00000000-0000-0000-0000-0000000000a1"
OID = "00000000-0000-0000-0000-0000000000b1"


def open_lead(**kw):
    return FakeResponse(200, {"leadid": LID, "subject": "Contoso inquiry", "companyname": "Contoso",
                              "statecode": 0, "statuscode": 1, **kw})


def test_qualify_body_flags_and_validation():
    b = lead.body(True, False, True)
    assert b == {"CreateAccount": True, "CreateContact": False, "CreateOpportunity": True,
                 "SuppressDuplicateDetection": False, "Status": 3}
    with pytest.raises(ValueError):
        lead.body(False, False, False)


def test_qualify_dry_run_sends_nothing(api, stub):
    stub.on("GET", r"^leads\(", open_lead())
    lines = []
    lead.qualify(api, LID, out=lines.append)
    assert stub.sent("POST") == [] and "dry run" in lines[-1]


def test_qualify_apply_posts_bound_action_then_verifies(api, stub):
    seq = iter([open_lead(), FakeResponse(200, {"statecode": 1, "statuscode": 3,
                                                 "_qualifyingopportunityid_value": "opp-1",
                                                 "_parentaccountid_value": "acc-1",
                                                 "_parentcontactid_value": "con-1"})])
    stub.on("GET", r"^leads\(", lambda req: next(seq))
    stub.on("POST", r"QualifyLead$", FakeResponse(200, {}))
    lines = []
    res = lead.qualify(api, LID, apply=True, out=lines.append)
    post = stub.sent("POST")[0]
    assert post["url"] == f"leads({LID})/Microsoft.Dynamics.CRM.QualifyLead"
    assert post["json"]["CreateOpportunity"] is True
    assert res["_qualifyingopportunityid_value"] == "opp-1" and "statecode 1" in lines[-1]


def test_qualify_refuses_a_lead_that_is_not_open(api, stub):
    stub.on("GET", r"^leads\(", open_lead(statecode=1))
    with pytest.raises(ValueError, match="not open"):
        lead.qualify(api, LID, apply=True)
    assert stub.sent("POST") == []


def test_qualify_404_points_to_doctor(api, stub):
    stub.on("GET", r"^leads\(", open_lead())
    stub.on("POST", r"QualifyLead$", not_found())
    lines = []
    with pytest.raises(DataverseError):
        lead.qualify(api, LID, apply=True, out=lines.append)
    assert any("doctor" in l for l in lines)


def test_find_open_escapes_quotes(api, stub):
    stub.on("GET", r"^leads\?", FakeResponse(200, {"value": []}))
    lead.find_open(api, email="o'neil@contoso.example")
    assert "emailaddress1 eq 'o''neil@contoso.example'" in stub.requests[0]["url"]


WHEN = dt.datetime(2027, 1, 15, 10, 0, tzinfo=dt.timezone.utc)


def test_close_body_won_defaults():
    b = close.close_body(OID, won=True, revenue=48000, when=WHEN, description="signed")
    assert b["Status"] == 3
    oc = b["OpportunityClose"]
    assert oc["@odata.type"] == "Microsoft.Dynamics.CRM.opportunityclose"
    assert oc["opportunityid@odata.bind"] == f"/opportunities({OID})"
    assert oc["actualrevenue"] == 48000 and oc["actualend"] == "2027-01-15T10:00:00Z"


def test_close_body_lost_status_depends_on_competitor():
    assert close.close_body(OID, won=False, revenue=None, when=WHEN)["Status"] == 4
    b = close.close_body(OID, won=False, revenue=None, when=WHEN, competitor_id="c1")
    assert b["Status"] == 5 and b["OpportunityClose"]["competitorid@odata.bind"] == "/competitors(c1)"


def test_close_body_rejects_bad_input():
    with pytest.raises(ValueError):
        close.close_body(OID, won=True, revenue=-1, when=WHEN)
    with pytest.raises(ValueError):
        close.close_body(OID, won=True, revenue=1, when=WHEN, status=5)


def test_close_apply_won(api, stub):
    seq = iter([FakeResponse(200, {"name": "Fabrikam", "statecode": 0}),
                FakeResponse(200, {"name": "Fabrikam", "statecode": 1, "statuscode": 3, "actualvalue": 48000,
                                   "msdyn_forecastcategory": 100000005,
                                   "msdyn_forecastcategory@OData.Community.Display.V1.FormattedValue": "Won"})])
    stub.on("GET", r"^opportunities\(", lambda req: next(seq))
    stub.on("POST", r"^WinOpportunity$", FakeResponse(204))
    lines = []
    res = close.close(api, OID, won=True, revenue=48000, when=WHEN, apply=True, out=lines.append)
    assert stub.sent("POST", "WinOpportunity") and res["statecode"] == 1
    assert "now Won" in lines[-1] and "forecast category Won" in lines[-1]


def test_close_lost_uses_loseopportunity_and_dry_run_is_silent(api, stub):
    stub.on("GET", r"^opportunities\(", FakeResponse(200, {"name": "Tailspin", "statecode": 0}))
    close.close(api, OID, won=False, when=WHEN, out=lambda *_: None)
    assert stub.sent("POST") == []
    stub.on("POST", r"^LoseOpportunity$", FakeResponse(204))
    close.close(api, OID, won=False, when=WHEN, apply=True, out=lambda *_: None)
    assert stub.sent("POST", "LoseOpportunity")


def test_close_refuses_closed_opportunity(api, stub):
    stub.on("GET", r"^opportunities\(", FakeResponse(200, {"name": "Done", "statecode": 1}))
    with pytest.raises(ValueError, match="already Won"):
        close.close(api, OID, won=True, apply=True)


CSDL = """<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0"><edmx:DataServices>
<Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Microsoft.Dynamics.CRM">
<EntityType Name="lead"/><EntityType Name="opportunity"/><EntityType Name="opportunityclose"/>
<EntityType Name="account"/><EntityType Name="contact"/>
<Action Name="QualifyLead" IsBound="true"><Parameter Name="entity" Type="mscrm.lead"/>
  <Parameter Name="CreateAccount" Type="Edm.Boolean"/><Parameter Name="Status" Type="Edm.Int32"/></Action>
<Action Name="WinOpportunity"><Parameter Name="Status" Type="Edm.Int32"/>
  <Parameter Name="OpportunityClose" Type="mscrm.crmbaseentity"/></Action>
</Schema></edmx:DataServices></edmx:Edmx>"""


def test_doctor_parse_reads_binding_and_params():
    info = doctor.parse(CSDL)
    q = info["actions"]["QualifyLead"]
    assert q["bound"] and q["binding"] == "mscrm.lead" and ("Status", "Edm.Int32") in q["params"]
    assert info["actions"]["WinOpportunity"]["bound"] is False and "LoseOpportunity" not in info["actions"]


def test_doctor_reports_missing_action(api, stub):
    stub.on("GET", r"^\$metadata$", FakeResponse(200, None, text=CSDL))
    lines = []
    assert doctor.check(api, out=lines.append) == 1
    assert any("LoseOpportunity" in l and "MISSING" in l for l in lines)
    assert any("QualifyLead" in l and "bound to mscrm.lead" in l for l in lines)
