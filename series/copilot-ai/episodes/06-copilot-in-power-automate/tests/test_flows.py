import copy
import json

import pytest

from copilot_flow_review.findings import worst
from copilot_flow_review.flows import definition_of, designer_blockers, load_flow, review_flow, walk_actions
from conftest import ROOT

SAMPLES = ROOT / "src" / "samples"
DRAFT = SAMPLES / "loan-reminders-draft.json"
REVIEWED = SAMPLES / "loan-reminders-reviewed.json"


def codes(findings):
    return sorted({f.code for f in findings})


def test_draft_flow_has_the_findings_a_first_copilot_pass_tends_to_leave():
    found = review_flow(load_flow(DRAFT))
    assert codes(found) == ["FR001", "FR002", "FR003", "FR005", "FR010"]
    fr001 = [f for f in found if f.code == "FR001"]
    assert len(fr001) == 1 and "facilities@contoso.example" in fr001[0].message
    # the borrower address is dynamic content: not flagged
    assert not any("BorrowerEmail" in f.message for f in fr001)
    fr010 = [f for f in found if f.code == "FR010"]
    assert len(fr010) == 1 and "DD-MM-YYYY" in fr010[0].message
    assert worst(found) == "warning"


def test_reviewed_flow_only_keeps_the_per_item_note():
    found = review_flow(load_flow(REVIEWED))
    assert codes(found) == ["FR003"]
    assert worst(found) == "info"


def test_walk_actions_finds_nested_actions_and_loop_flag():
    d = definition_of(load_flow(REVIEWED))
    items = {path: in_loop for path, _, in_loop in walk_actions(d["actions"])}
    assert items["Try/Apply_to_each/Send_reminder"] is True
    assert items["Try/Get_overdue_loans"] is False
    assert "Catch/Send_failure_notice" in items


def test_failure_path_can_be_a_sibling_branch_anywhere():
    flow = load_flow(DRAFT)
    flow["properties"]["definition"]["actions"]["Notify_failure"] = {
        "type": "Compose", "runAfter": {"Post_summary": ["Failed"]}, "inputs": "failed"}
    assert "FR002" not in codes(review_flow(flow))


def test_read_only_flow_does_not_need_a_failure_path():
    flow = {"triggers": {"manual": {"type": "Request", "kind": "Button"}},
            "actions": {"Get": {"type": "OpenApiConnection", "runAfter": {}, "inputs": {"host": {"operationId": "GetItems"}}}}}
    assert review_flow(flow) == []


def test_recurrence_with_time_zone_is_fine():
    flow = load_flow(DRAFT)
    flow["properties"]["definition"]["triggers"]["Every_weekday_at_8"]["recurrence"]["timeZone"] = "GMT Standard Time"
    assert "FR005" not in codes(review_flow(flow))


@pytest.mark.parametrize("value,flagged", [
    ("someone@contoso.example", True),
    ("a@contoso.example; b@contoso.example", True),
    ("@parameters('ReminderCc')", False),
    ("@{items('x')?['Mail']}", False),
    ("not an address", False),
])
def test_literal_recipient_detection(value, flagged):
    flow = copy.deepcopy(load_flow(DRAFT))
    flow["properties"]["definition"]["actions"]["Apply_to_each"]["actions"]["Send_reminder"]["inputs"]["parameters"]["emailMessage/Cc"] = value
    assert ("FR001" in codes(review_flow(flow))) is flagged


def test_legacy_connection_type_blocks_the_copilot_designer():
    flow = copy.deepcopy(load_flow(REVIEWED))
    flow["properties"]["definition"]["actions"]["Try"]["actions"]["Get_overdue_loans"]["type"] = "ApiConnection"
    found = designer_blockers(flow)
    assert [f.code for f in found] == ["FR008"]
    assert "Copilot" in found[0].message


def test_connection_without_reference_blocks_the_copilot_designer():
    flow = copy.deepcopy(load_flow(REVIEWED))
    flow["properties"]["connectionReferences"]["shared_teams"]["connection"] = {"name": "shared-teams-00000000"}
    found = designer_blockers(flow)
    assert [f.code for f in found] == ["FR009"]
    assert "shared_teams" in found[0].where


def test_bare_definition_is_accepted_and_garbage_is_rejected():
    bare = load_flow(REVIEWED)["properties"]["definition"]
    assert definition_of(bare) is bare
    with pytest.raises(ValueError):
        definition_of({"hello": "world"})


def test_sample_files_use_zero_guids_and_example_domains_only():
    import re
    text = DRAFT.read_text() + REVIEWED.read_text()
    assert "00000000-0000-0000-0000-000000000000" in text
    domains = set(re.findall(r"@([a-z0-9]+(?:\.[a-z0-9]+)*\.[a-z]{2,})", text))
    assert {d for d in domains if not d.endswith(".example") and not d.startswith("thread.tacv")} == set()
    json.loads(DRAFT.read_text())
    json.loads(REVIEWED.read_text())
