"""Audit findings, the Web API exporter and the RetrievePrincipalAccess verifier (with a stub API: no tenant)."""
import pytest
import requests

from rolecheck import model as m
from rolecheck.audit import audit
from rolecheck.cli import main
from rolecheck.export import export_model, parse_privilege_name
from rolecheck.verify import compare, principal_access, render
from rolecheck.webapi import WebApi, WebApiError

Z = "00000000-0000-0000-0000-0000000000"   # + two digits: fictional zero GUIDs


def g(n):
    return f"{Z}{n:02d}"


# ---------- audit ----------
def test_audit_flags_org_wide_delete_and_users_without_privileges(sm):
    findings = audit(sm)
    checks = [(f.severity, f.check, f.subject) for f in findings]
    assert checks[0] == ("High", "org-wide-destructive", "role 'Bulk Cleanup'")
    assert ("Medium", "no-privileges", "user 'Eva Placeholder'") in checks
    assert ("Info", "team-only-user", "user 'Diego Demo'") in checks


def test_audit_flags_team_records_nobody_in_the_team_can_read(raw):
    raw["teams"][0]["roles"] = []
    findings = audit(m.from_dict(raw))
    assert any(f.check == "unreadable-team-records" and "PR-0002" in f.detail for f in findings)


def test_audit_cli_exit_code_fails_the_pipeline_on_high(capsys):
    assert main(["audit"]) == 1
    assert "1 high" in capsys.readouterr().out


# ---------- export ----------
def test_parse_privilege_name():
    assert parse_privilege_name("prvAppendTomgl_ProjectRequest") == ("AppendTo", "mgl_projectrequest")
    assert parse_privilege_name("prvAppendmgl_ProjectRequest") == ("Append", "mgl_projectrequest")
    assert parse_privilege_name("prvReadAccount") == ("Read", "account")
    assert parse_privilege_name("prvPublishDuplicateRule") is None


class StubApi:
    """Answers the exporter's GETs with payloads shaped like the Learn examples."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, path, annotations=False):
        self.calls.append(path)
        for prefix, payload in self.routes.items():
            if path.startswith(prefix):
                return payload
        raise AssertionError(f"unexpected GET {path}")

    def get_all(self, path, annotations=False):
        yield from self.get(path, annotations).get("value", [])


@pytest.fixture
def stub():
    return StubApi({
        "businessunits": {"value": [
            {"businessunitid": g(1), "name": "Contoso", "_parentbusinessunitid_value": None},
            {"businessunitid": g(2), "name": "Sales", "_parentbusinessunitid_value": g(1)}]},
        "EntityDefinitions(LogicalName='mgl_projectrequest')": {
            "OwnershipType": "UserOwned", "EntitySetName": "mgl_projectrequests", "PrimaryIdAttribute": "mgl_projectrequestid"},
        "systemusers": {"value": [
            {"systemuserid": g(10), "fullname": "Alex Demo", "_businessunitid_value": g(2),
             "systemuserroles_association": [{"roleid": g(20)}]},
            {"systemuserid": g(11), "fullname": "Diego Demo", "_businessunitid_value": g(2),
             "systemuserroles_association": []}]},
        "teams": {"value": [
            {"teamid": g(30), "name": "PMO", "teamtype": 0, "_businessunitid_value": g(2),
             "teamroles_association": [{"roleid": g(21)}], "teammembership_association": [{"systemuserid": g(11)}]},
            {"teamid": g(31), "name": "Deal room", "teamtype": 1, "_businessunitid_value": g(2),
             "teamroles_association": [], "teammembership_association": [{"systemuserid": g(10)}]}]},
        f"roles({g(20)})": {"roleid": g(20), "name": "Project Requester", "isinherited": 1, "_businessunitid_value": g(1)},
        f"roles({g(21)})": {"roleid": g(21), "name": "PMO Team Member", "isinherited": 0, "_businessunitid_value": g(1)},
        f"RetrieveRolePrivilegesRole(RoleId={g(20)})": {"RolePrivileges": [
            {"Depth": "Basic", "PrivilegeId": g(40), "BusinessUnitId": g(1), "PrivilegeName": "prvReadmgl_ProjectRequest"},
            {"Depth": "Basic", "PrivilegeId": g(41), "BusinessUnitId": g(1), "PrivilegeName": "prvWritemgl_ProjectRequest"},
            {"Depth": "Global", "PrivilegeId": g(42), "BusinessUnitId": g(1), "PrivilegeName": "prvReadAccount"}]},
        f"RetrieveRolePrivilegesRole(RoleId={g(21)})": {"RolePrivileges": [
            {"Depth": "Basic", "PrivilegeId": g(40), "BusinessUnitId": g(1), "PrivilegeName": None},
            {"Depth": "RecordFilter", "PrivilegeId": g(41), "BusinessUnitId": g(1),
             "PrivilegeName": "prvWritemgl_ProjectRequest"}]},
        "privileges": {"value": [{"privilegeid": g(40), "name": "prvReadmgl_ProjectRequest"}]},
        "mgl_projectrequests": {"value": [
            {"mgl_projectrequestid": g(50), "_ownerid_value": g(30), "_owningbusinessunit_value": g(2),
             "_ownerid_value@Microsoft.Dynamics.CRM.lookuplogicalname": "team"},
            {"mgl_projectrequestid": g(51), "_ownerid_value": g(99), "_owningbusinessunit_value": g(2),
             "_ownerid_value@Microsoft.Dynamics.CRM.lookuplogicalname": "systemuser"}]},
        "RetrieveSharedPrincipalsAndAccess": {"PrincipalAccesses": [
            {"AccessMask": "ReadAccess, WriteAccess",
             "Principal": {"@odata.type": "#Microsoft.Dynamics.CRM.team", "ownerid": g(31)}}]},
    })


def test_export_builds_a_valid_model_with_depths_teams_and_shares(stub):
    warnings = []
    data = export_model(stub, ["mgl_projectrequest"], warn=warnings.append)
    sm = m.from_dict(data)                                       # passes validation
    req = sm.roles[g(20)]
    assert req.privileges == {"mgl_projectrequest": {"Read": m.Depth.USER, "Write": m.Depth.USER}}  # Account ignored
    pmo = sm.roles[g(21)]
    assert pmo.inherited is False and pmo.privileges["mgl_projectrequest"] == {"Read": m.Depth.USER}
    assert sm.teams[g(31)].type == "access" and sm.teams[g(30)].members == [g(11)]
    assert sm.records[g(50)].owner == m.Principal("team", g(30))
    assert g(51) not in sm.records                               # owner not exported -> skipped with a warning
    assert any("RecordFilter" in w for w in warnings) and any(g(51) in w for w in warnings)
    assert sm.shares[0].rights == {"Read", "Write"}
    assert any(c.startswith("privileges") for c in stub.calls)   # name fallback used once


def test_export_never_calls_retrieve_user_privileges(stub):
    export_model(stub, ["mgl_projectrequest"], warn=lambda s: None)
    assert not any("RetrieveUserPrivileges" in c for c in stub.calls)


# ---------- verify ----------
def test_principal_access_parses_access_rights_flags():
    api = StubApi({"systemusers(": {"AccessRights": "ReadAccess, WriteAccess, AppendAccess, AppendToAccess"}})
    rights = principal_access(api, g(10), "mgl_projectrequests", g(50))
    assert rights == {"Read", "Write", "Append", "AppendTo"}
    assert api.calls[0] == (f"systemusers({g(10)})/Microsoft.Dynamics.CRM.RetrievePrincipalAccess(Target=@p1)"
                            f"?@p1={{'@odata.id':'mgl_projectrequests({g(50)})'}}")


def test_compare_marks_differences(sm, uid):
    rows, same = compare(sm, {"Read", "Write", "Append", "AppendTo"}, uid("Alex Demo"), "PR-0001")
    assert same
    rows, same = compare(sm, {"Read"}, uid("Alex Demo"), "PR-0001")
    assert not same and any("<-- differs" in line for line in render(rows))


# ---------- web api ----------
class Resp:
    def __init__(self, status, payload, headers=None):
        self.status_code, self._p, self.headers, self.text = status, payload, headers or {}, str(payload)

    def json(self):
        return self._p


def test_webapi_retries_429_and_follows_next_link():
    seq = [Resp(429, {}, {"Retry-After": "3"}),
           Resp(200, {"value": [1, 2], "@odata.nextLink": "https://contoso/api/data/v9.2/x?$skiptoken=a"}),
           Resp(200, {"value": [3]})]
    s = requests.Session()
    s.get = lambda url, headers: seq.pop(0)
    sleeps = []
    api = WebApi("https://contoso", lambda: "t", session=s, sleep=sleeps.append)
    assert list(api.get_all("x")) == [1, 2, 3] and sleeps == [3.0]


def test_webapi_raises_with_the_server_message():
    s = requests.Session()
    s.get = lambda url, headers: Resp(403, {"error": {"code": "0x80040220", "message": "Principal user is missing prvReadRole"}})
    with pytest.raises(WebApiError, match="missing prvReadRole"):
        WebApi("https://contoso", lambda: "t", session=s).get("roles")
