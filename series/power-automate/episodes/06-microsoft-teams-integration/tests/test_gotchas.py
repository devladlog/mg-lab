"""The traps, reproduced: card JSON built from text, the Flow bot budget, private channels, renamed buttons,
and why the join at the end has a check inside it."""
import copy

from flowkit import lint
from teamsfake import PRIVATE_CHANNEL, Dispatch, Response, it_request
from teamsfake.variants import all_posts_as_flow_bot, card_as_string_template

from conftest import SAM, actions, card_sent


def test_a_quote_in_the_title_breaks_a_pasted_card(flow):
    title = 'Monitor 27" flickers on the left side'
    draft = Dispatch(card_as_string_template(flow))
    r = draft.run(it_request(45, title), Response(SAM, "Take it"))
    assert r.status_of("Ask_on_call") == "Failed" and "isn't valid JSON" in r.actions["Ask_on_call"].error
    assert r.status == "Failed" and r.terminate_error["code"] == "CardNotPosted"
    final = Dispatch(flow)
    r = final.run(it_request(45, title), Response(SAM, "Take it"))
    assert r.status == "Succeeded" and card_sent(r)["body"][1]["text"] == title


def test_a_backslash_is_worse_it_silently_changes_the_text(flow):
    title = r"Can't save to C:\temp\new"
    draft = Dispatch(card_as_string_template(flow))
    r = draft.run(it_request(46, title), Response(SAM, "Take it"))
    assert r.status == "Succeeded"                       # valid JSON...
    assert card_sent(r)["body"][1]["text"] == "Can't save to C:\temp\new"   # ...with a tab and a line break
    r = Dispatch(flow).run(it_request(46, title), Response(SAM, "Take it"))
    assert card_sent(r)["body"][1]["text"] == title


def test_flow_bot_budget_is_25_posts_per_five_minutes(flow):
    def burst(f, n=20):
        d = Dispatch(f)
        results = []
        for i in range(n):
            results.append(d.run(it_request(100 + i, f"Outage report {i + 1}"), Response(SAM, "Take it")))
            d.teams.tick(300 / n)
        return d, results

    d, results = burst(all_posts_as_flow_bot(flow))      # card + announcement, both as Flow bot
    assert sum(r.status == "Failed" for r in results) == 8
    assert d.teams.throttled("Flow bot") == 8
    d, results = burst(flow)                              # card as Flow bot, announcement as User
    assert all(r.status == "Succeeded" for r in results)
    assert d.teams.throttled("Flow bot") == 0
    d, results = burst(flow, 30)                          # still a limit: 30 cards in five minutes
    assert sum(r.status == "Failed" for r in results) == 5


def test_private_channels_arent_supported_and_the_run_says_so(dispatch):
    dispatch.params["On-call channel ID (cts_OnCallChannelId)"] = PRIVATE_CHANNEL
    r = dispatch.run(it_request(42), Response(SAM, "Take it"))
    assert "private channel" in r.actions["Ask_on_call"].error
    assert r.status == "Failed" and r.terminate_error["code"] == "CardNotPosted"


def test_the_join_without_its_check_hides_a_failed_post(flow):
    hidden = copy.deepcopy(flow)
    actions(hidden)["Dispatch_done"]["actions"] = {}
    d = Dispatch(hidden)
    d.params["On-call channel ID (cts_OnCallChannelId)"] = PRIVATE_CHANNEL
    r = d.run(it_request(42), Response(SAM, "Take it"))
    assert r.status_of("Ask_on_call") == "Failed"
    assert r.status == "Succeeded"                       # nothing posted, nobody told, run is green


def test_without_the_join_a_handled_timeout_fails_the_run(flow):
    no_join = copy.deepcopy(flow)
    del actions(no_join)["Dispatch_done"]
    r = Dispatch(no_join).run(it_request(44), Response(None))
    assert r.status_of("Escalate_to_lead") == "Succeeded"   # the lead was told...
    assert r.status == "Failed"                             # ...but Route response is a skipped last action
    assert any("is skipped and, as the last action of its branch" in f.message for f in lint(no_join))


def test_renaming_a_button_breaks_the_switch(flow):
    renamed = copy.deepcopy(flow)
    actions(renamed)["Build_card"]["inputs"]["actions"][0]["title"] = "I'll take it"
    r = Dispatch(renamed).run(it_request(42), Response(SAM, "I'll take it"))
    assert r.status == "Failed" and r.terminate_error["code"] == "UnexpectedResponse"
    assert "I'll take it" in r.terminate_error["message"]
