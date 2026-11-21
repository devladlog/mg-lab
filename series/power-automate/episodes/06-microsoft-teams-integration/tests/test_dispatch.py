"""Every path of the on-call card: taken, more info needed, nobody answers, filtered out by the trigger."""
from flowkit.cards import card_problems

from teamsfake import Response, it_request

from conftest import RILEY, SAM, card_sent


def test_take_it_assigns_the_request_and_announces_the_owner(dispatch):
    r = dispatch.run(it_request(42), Response(SAM, "Take it"))
    assert r.status == "Succeeded"
    assert r.variables["dispatch"] == "taken by Sam Demo"
    (update,) = dispatch.helpdesk.updates
    assert update["id"] == 42 and update["item/AssignedTo/Claims"] == "i:0#.f|membership|sam.demo@contoso.com"
    card, announcement = dispatch.channel.messages
    assert card["poster"] == "Flow bot" and card["kind"] == "updated card"
    assert card["content"] == "Request #42 has been picked up. Who took it is posted in this channel."
    assert announcement["poster"] == "User"
    assert announcement["content"] == ("<p><at>Sam Demo</at> took high priority request #42: "
                                       "Laptop won't boot before a client demo</p>")


def test_need_more_info_messages_the_requester_with_the_note(dispatch):
    r = dispatch.run(it_request(43, "VPN drops every 10 minutes"), Response(RILEY, "Need more info", "Office or home?"))
    assert r.status == "Succeeded" and r.variables["dispatch"] == "more info requested by Riley Demo"
    assert dispatch.helpdesk.updates == []
    (chat,) = dispatch.teams.chats["alex.demo@contoso.com"]
    assert chat["poster"] == "Flow bot"
    assert "<p>Office or home?</p>" in chat["content"] and "reply to Riley Demo" in chat["content"]


def test_an_empty_note_says_so(dispatch):
    dispatch.run(it_request(43), Response(RILEY, "Need more info", ""))
    (chat,) = dispatch.teams.chats["alex.demo@contoso.com"]
    assert "<p>(no note)</p>" in chat["content"]


def test_nobody_answers_in_30_minutes_the_lead_is_mentioned(dispatch, flow):
    assert flow["properties"]["definition"]["actions"]["Ask_on_call"]["limit"] == {"timeout": "PT30M"}
    r = dispatch.run(it_request(44, "Shared printer offline before payroll"), Response(None))
    assert r.status_of("Ask_on_call") == "TimedOut"
    assert r.status == "Succeeded"                       # handled: the join keeps the run green
    assert r.variables["dispatch"] == "escalated to the on-call lead"
    card, escalation = dispatch.channel.messages
    assert card["kind"] == "card"                        # no answer, so the card was never replaced
    assert escalation["content"].startswith("<p><at>Taylor Demo</at> nobody has taken high priority request #44")
    assert dispatch.helpdesk.updates == []


def test_only_high_priority_real_requests_start_a_run(dispatch):
    assert dispatch.run(it_request(45, priority="Normal")).status == "Skipped"
    assert dispatch.run(it_request(46, "[TEST] please ignore")).status == "Skipped"
    assert dispatch.run(it_request(47, "[test] lower case too")).status == "Skipped"   # startsWith ignores case
    assert dispatch.channel.messages == []


def test_the_card_is_valid_and_shows_the_request(dispatch):
    r = dispatch.run(it_request(42), Response(SAM, "Take it"))
    card = card_sent(r)
    assert card_problems(r.actions["Ask_on_call"].inputs["parameters"]["body/body/messageBody"], True) == []
    assert card["version"] == "1.4"
    assert card["body"][0]["text"] == "High priority IT request #42"
    facts = {f["title"]: f["value"] for f in card["body"][2]["facts"]}
    assert facts == {"Category": "Hardware", "Raised by": "Alex Demo", "Raised at": "2026-01-05 08:58 UTC"}
    assert [a["title"] for a in card["actions"]] == ["Take it", "Need more info", "Open the request"]
