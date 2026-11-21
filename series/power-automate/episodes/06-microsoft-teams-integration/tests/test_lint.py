"""Teams lint rules (Learn: Teams connector known issues, adaptive cards known issues)."""
import copy
import json

from flowkit import lint
from teamsfake.variants import card_as_string_template

from conftest import actions


def messages(flow, level=None):
    return [f.message for f in lint(flow) if level is None or f.level == level]


def test_the_solution_flow_is_clean(flow):
    assert lint(flow) == []


def test_a_wait_for_response_card_needs_a_timeout_and_a_handler(flow):
    bad = copy.deepcopy(flow)
    del actions(bad)["Ask_on_call"]["limit"]
    assert any("without a timeout waits until the 30-day run limit" in m for m in messages(bad, "warning"))
    bad = copy.deepcopy(flow)
    del actions(bad)["Escalate_to_lead"]
    actions(bad)["Dispatch_done"]["runAfter"].pop("Escalate_to_lead")
    assert any("nothing runs after it 'has timed out'" in m for m in messages(bad, "warning"))


def test_card_json_built_from_text_is_flagged(flow):
    assert any("string interpolation" in m for m in messages(card_as_string_template(flow), "warning"))


def test_static_cards_are_checked(flow):
    bad = copy.deepcopy(flow)
    card = {"type": "AdaptiveCard", "version": "1.4", "$data": {"title": "x"},
            "body": [{"type": "TextBlock", "text": "${title}"}],
            "actions": [{"type": "Action.Submit", "title": "OK"}]}
    p = actions(bad)["Ask_on_call"]["inputs"]["parameters"]
    p["body/body/messageBody"] = json.dumps(card)
    assert any("templating" in m for m in messages(bad, "error"))


def test_every_connector_is_solution_aware(flow):
    refs = flow["properties"]["connectionReferences"]
    assert set(refs) == {"shared_sharepointonline", "shared_teams"}
    assert all(r["connection"]["connectionReferenceLogicalName"].startswith("cts_") for r in refs.values())


def test_channel_and_team_come_from_environment_variables(flow):
    p = actions(flow)["Ask_on_call"]["inputs"]["parameters"]
    assert p["body/body/recipient/groupId"] == "@parameters('On-call team ID (cts_OnCallTeamId)')"
    assert p["body/body/recipient/channelId"] == "@parameters('On-call channel ID (cts_OnCallChannelId)')"
