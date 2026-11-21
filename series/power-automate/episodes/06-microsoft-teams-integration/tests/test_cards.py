"""The adaptive card checks on their own."""
import json

from flowkit.cards import card_problems, mention_count

OK = {"type": "AdaptiveCard", "version": "1.4", "body": [{"type": "Input.Text", "id": "note"}],
      "actions": [{"type": "Action.Submit", "title": "Take it"}]}


def card(**changes):
    c = json.loads(json.dumps(OK))
    c.update(changes)
    return json.dumps(c)


def test_a_minimal_wait_card_is_fine():
    assert card_problems(card(), waits_for_response=True) == []


def test_submit_buttons_need_a_wait_action():
    assert any("only works on cards posted with" in p for p in card_problems(card(), waits_for_response=False))


def test_a_wait_card_without_buttons_cant_be_answered():
    assert any("needs at least one Action.Submit" in p for p in card_problems(card(actions=[]), True))


def test_duplicate_titles_and_ids():
    c = card(actions=[{"type": "Action.Submit", "title": "OK"}, {"type": "Action.Submit", "title": "OK"}],
             body=[{"type": "Input.Text", "id": "a"}, {"type": "Input.Text", "id": "a"}])
    problems = card_problems(c, True)
    assert any("titled 'OK'" in p for p in problems) and any("input id 'a'" in p for p in problems)


def test_size_limit_is_about_28_kb():
    big = card(body=[{"type": "TextBlock", "text": "x" * 29000}])
    assert any("Request Entity too large" in p for p in card_problems(big, True))


def test_not_json_or_not_a_card():
    assert "isn't valid JSON" in card_problems('{"type": "AdaptiveCard",', True)[0]
    assert "AdaptiveCard" in card_problems('{"type": "MessageCard"}', True)[0]


def test_mentions_are_counted():
    assert mention_count("<p><at>Sam Demo</at> and <AT>Riley Demo</AT></p>") == 2
