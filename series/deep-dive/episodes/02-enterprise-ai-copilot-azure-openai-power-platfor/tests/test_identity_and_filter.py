import base64
import json

import pytest
from conftest import ALEX, EMPLOYEES, MANAGERS, principal

from copilot.identity import Caller, GroupOverage, Unauthenticated, parse_client_principal
from copilot.retrieval import security_filter


def test_reads_oid_name_and_groups():
    c = parse_client_principal(principal(groups=(MANAGERS, EMPLOYEES)))
    assert c == Caller(object_id=ALEX, name="alex.demo@contoso.com", groups=(EMPLOYEES, MANAGERS))


def test_accepts_the_mapped_claim_names_app_service_uses():
    c = parse_client_principal(principal(mapped=True))
    assert c.object_id == ALEX and c.groups == (EMPLOYEES,)


@pytest.mark.parametrize("value", [None, "", "not-base64!!", base64.b64encode(b"[]").decode(),
                                   base64.b64encode(b'{"claims": []}').decode()])
def test_missing_or_malformed_principal_is_unauthenticated(value):
    with pytest.raises(Unauthenticated):
        parse_client_principal(value)


def test_principal_without_object_id_is_rejected():
    doc = {"auth_typ": "aad", "claims": [{"typ": "groups", "val": EMPLOYEES}]}
    with pytest.raises(Unauthenticated):
        parse_client_principal(base64.b64encode(json.dumps(doc).encode()).decode())


def test_group_overage_fails_closed():
    overage = [{"typ": "_claim_names", "val": '{"groups":"src1"}'}]
    with pytest.raises(GroupOverage):
        parse_client_principal(principal(groups=(), extra=overage))


def test_hasgroups_overage_fails_closed():
    with pytest.raises(GroupOverage):
        parse_client_principal(principal(groups=(), extra=[{"typ": "hasgroups", "val": "true"}]))


def test_non_guid_group_values_are_dropped():
    c = parse_client_principal(principal(groups=(EMPLOYEES, "HR Managers", "x' or 1 eq 1")))
    assert c.groups == (EMPLOYEES,)


def test_filter_matches_the_documented_search_in_pattern():
    assert security_filter((EMPLOYEES, MANAGERS)) == (
        f"group_ids/any(g: search.in(g, '{EMPLOYEES},{MANAGERS}', ','))")


def test_filter_refuses_empty_groups():
    with pytest.raises(ValueError, match="unfiltered"):
        security_filter(())


@pytest.mark.parametrize("evil", ["') or true or ('", "a', ' '), search.in(g, '*", EMPLOYEES + "'"])
def test_filter_refuses_anything_that_is_not_a_guid(evil):
    with pytest.raises(ValueError):
        security_filter((evil,))
