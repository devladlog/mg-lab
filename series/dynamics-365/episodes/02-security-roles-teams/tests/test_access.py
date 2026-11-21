"""The documented access algorithm on the fictional Contoso model: one test per rule."""
import copy

import pytest

from rolecheck import model as m
from rolecheck.access import explain, who_has_access
from rolecheck.model import Depth


def test_depth_accepts_ui_and_api_names():
    assert Depth.parse("User") == Depth.parse("Basic") == Depth.USER
    assert Depth.parse("Business Unit") == Depth.parse("Local") == Depth.BUSINESS_UNIT
    assert Depth.parse("Parent: Child Business Units") == Depth.parse("Deep") == Depth.PARENT_CHILD
    assert Depth.parse("Organization") == Depth.parse("Global") == Depth.ORGANIZATION
    with pytest.raises(ValueError):
        Depth.parse("Everything")


def test_owner_with_user_level_privilege_can_write(sm, uid):
    d = explain(sm, uid("Alex Demo"), "PR-0001", "Write")
    assert d.allowed and d.privilege_check
    assert d.paths == ["ownership: user owns the record; role 'Project Requester' at User level"]


def test_user_level_does_not_reach_a_colleagues_record(sm, uid):
    d = explain(sm, uid("Gil Sample"), "PR-0001", "Read")
    assert not d.allowed and d.privilege_check
    assert any("User level only covers records the user" in r for r in d.reasons)


def test_privilege_check_comes_first_even_for_the_owner(sm, uid):
    d = explain(sm, uid("Alex Demo"), "PR-0001", "Delete")
    assert not d.allowed and not d.privilege_check


def test_share_with_an_access_team_grants_the_shared_rights(sm, uid):
    d = explain(sm, uid("Alex Demo"), "PR-0004", "Read")
    assert d.allowed and d.paths[0].startswith("shared access: record shared with PR-0004 deal room")


def test_share_does_not_grant_rights_that_were_not_shared(sm, uid, raw):
    raw["roles"][0]["privileges"]["mgl_projectrequest"]["Delete"] = "User"
    sm2 = m.from_dict(raw)
    d = explain(sm2, uid("Alex Demo"), "PR-0004", "Delete")
    assert not d.allowed and any("only for Append, Read, Write" in r for r in d.reasons)


def test_share_without_any_role_fails_the_privilege_check(sm, uid):
    """The gotcha: Eva is in the access team the record is shared with, but has no role at all."""
    d = explain(sm, uid("Eva Placeholder"), "PR-0004", "Read")
    assert not d.allowed and not d.privilege_check
    assert any("teams that don't have roles give no privileges" in r for r in d.reasons)


def test_team_privileges_only_role_works_on_team_owned_records(sm, uid):
    d = explain(sm, uid("Diego Demo"), "PR-0002", "Write")
    assert d.allowed and "member of owner team 'PMO Lisbon'" in d.paths[0]


def test_team_privileges_only_role_does_not_work_elsewhere(sm, uid):
    d = explain(sm, uid("Diego Demo"), "PR-0001", "Read")
    assert not d.allowed and d.privilege_check
    assert any("only usable on records owned by that team" in r for r in d.reasons)


def test_direct_user_basic_inheritance_lets_members_use_it_on_their_own_records(raw, uid):
    raw["roles"][3]["inherited"] = True                          # PMO Team Member -> Direct User (Basic) ...
    raw["records"].append({"table": "mgl_projectrequest", "id": "PR-0099", "owner": {"type": "user", "id": "u-diego"}})
    sm2 = m.from_dict(raw)
    assert explain(sm2, "u-diego", "PR-0099", "Write").allowed
    raw["roles"][3]["inherited"] = False                         # ... and back to Team privileges only
    assert not explain(m.from_dict(raw), "u-diego", "PR-0099", "Write").allowed


def test_team_role_levels_are_measured_from_the_team_business_unit(sm, uid):
    read = explain(sm, uid("Bruno Example"), "PR-0001", "Read")      # Parent: Child from 'Sales' reaches Sales Portugal
    write = explain(sm, uid("Bruno Example"), "PR-0001", "Write")    # Business Unit 'Sales' does not
    assert read.allowed and "is 'Sales' or below it" in read.paths[0]
    assert not write.allowed and "covers 'Sales' only, record is in 'Sales Portugal'" in write.reasons[0]


def test_parent_child_does_not_reach_a_sibling_business_unit(sm, uid):
    assert not explain(sm, uid("Bruno Example"), "PR-0005", "Read").allowed   # Finance is not under Sales


def test_organization_level_reads_everywhere(sm, uid):
    for rec in ("PR-0001", "PR-0002", "PR-0003", "PR-0004", "PR-0005"):
        assert explain(sm, uid("Carla Test"), rec, "Read").allowed


def test_organization_owned_table_is_only_a_privilege_check(sm, uid):
    assert explain(sm, uid("Carla Test"), "CC-100", "Write").allowed
    assert explain(sm, uid("Alex Demo"), "CC-100", "Read").allowed
    assert not explain(sm, uid("Alex Demo"), "CC-100", "Write").allowed


def test_access_can_come_from_several_paths_at_once(raw):
    raw["users"][0]["roles"].append("r-finance-controller")       # Alex: owner AND organization reader
    d = explain(m.from_dict(raw), "u-alex", "PR-0001", "Read")
    kinds = [p.split(":")[0] for p in d.paths]
    assert kinds == ["ownership", "ownership", "role access"]   # owner via each role, plus Organization-level reach


def test_disabled_users_have_no_access(raw):
    raw["users"][0]["disabled"] = True
    assert not explain(m.from_dict(raw), "u-alex", "PR-0001", "Read").allowed


def test_org_wide_share_reaches_every_user_with_the_privilege(raw):
    raw["shares"].append({"record": "PR-0005", "principal": {"type": "organization"}, "rights": ["Read"]})
    sm2 = m.from_dict(raw)
    assert explain(sm2, "u-gil", "PR-0005", "Read").allowed
    assert not explain(sm2, "u-eva", "PR-0005", "Read").allowed    # still no privilege


def test_who_has_access_lists_users_with_their_first_path(sm):
    rows = who_has_access(sm, "PR-0001", "Read")
    assert [r[0] for r in rows] == ["Alex Demo", "Bruno Example", "Carla Test", "Filipe Contoso"]


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["teams"][2]["roles"].append("r-requester"), "access teams don't have security roles"),
    (lambda d: d["records"].append({"table": "mgl_projectrequest", "id": "X", "owner": {"type": "team", "id": "t-dealroom"}}),
     "access teams can't own records"),
    (lambda d: d["roles"][0]["privileges"]["mgl_costcenter"].update({"Read": "BusinessUnit"}),
     "can only be Organization or None"),
    (lambda d: d["business_units"].append({"id": "bu-x", "name": "Orphan", "parent": None}), "exactly one root"),
    (lambda d: d["users"][0]["roles"].append("r-missing"), "unknown role"),
])
def test_model_validation(raw, mutate, message):
    data = copy.deepcopy(raw)
    mutate(data)
    with pytest.raises(m.ModelError, match=message):
        m.from_dict(data)
