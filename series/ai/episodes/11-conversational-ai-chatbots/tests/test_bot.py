import json

import pytest

from conftest import call, say
from helpbot.bot import FILTERED_REPLY, HANDOFF_REPLY, WAITING_REPLY, Bot
from helpbot.session import Session

GOOD = {"product": "Contoso Connect VPN", "symptom": "drops every five minutes", "urgency": "high", "contact": "alex.demo@contoso.com"}


def test_a_plain_answer_is_streamed_token_by_token_and_stored(bot, stub):
    stub.model = lambda req: say("Restart the VPN client and try again.")
    s, tokens = Session(), []
    r = bot.reply(s, "VPN is slow", on_token=tokens.append)
    assert r.text == "Restart the VPN client and try again." and len(tokens) > 3 and "".join(tokens) == r.text
    assert [m["role"] for m in s.messages] == ["user", "assistant"] and r.model_calls == 1


def test_the_request_is_keyless_streamed_with_usage_capped_and_tools_attached(bot, stub, cred):
    bot.reply(Session(), "hello")
    rec = stub.requests[0]
    req = rec["json"]
    assert rec["auth"] == "Bearer fake-entra-token" and cred.scopes == ["https://ai.azure.com/.default"]
    assert req["model"] == "chat" and req["stream"] is True and req["stream_options"] == {"include_usage": True}
    assert req["max_completion_tokens"] == 300 and req["temperature"] == 0
    assert {t["function"]["name"] for t in req["tools"]} == {"create_ticket", "handoff_to_human"}
    assert req["messages"][0]["role"] == "system" and req["messages"][-1] == {"role": "user", "content": "hello"}


def test_billed_usage_comes_from_the_final_stream_chunk_and_is_compared_with_our_estimate(bot, stub):
    r = bot.reply(Session(), "hello")
    assert r.prompt_tokens > 0 and r.first_prompt_tokens == r.prompt_tokens and r.estimated_prompt_tokens > 0


def test_tool_loop_opens_a_ticket_and_sends_the_tool_result_back_with_its_call_id(bot, stub):
    answers = iter([call("create_ticket", GOOD, "call_77"), say("Done: INC-1001 is open.")])
    stub.model = lambda req: next(answers)
    s = Session()
    r = bot.reply(s, "please open it")
    assert s.tickets[0]["ticket_id"] == "INC-1001" and r.text == "Done: INC-1001 is open." and r.model_calls == 2
    second = stub.chats()[1]["messages"]
    assert second[-1] == {"role": "tool", "tool_call_id": "call_77", "content": json.dumps({"ok": True, "ticket_id": "INC-1001"})}
    assert second[-2]["tool_calls"][0]["id"] == "call_77"


def test_a_ticket_with_missing_slots_returns_the_error_to_the_model_and_creates_nothing(bot, stub):
    answers = iter([call("create_ticket", {"product": "VPN"}), say("What is your e-mail address?")])
    stub.model = lambda req: next(answers)
    s = Session()
    r = bot.reply(s, "open a ticket")
    assert s.tickets == [] and "e-mail" in r.text
    assert json.loads(stub.chats()[1]["messages"][-1]["content"])["missing"] == ["symptom", "urgency", "contact"]


def test_garbage_tool_arguments_do_not_crash_the_turn(bot, stub):
    answers = iter([call("create_ticket", "{oops"), say("Sorry, let me ask again: which product?")])
    stub.model = lambda req: next(answers)
    r = bot.reply(Session(), "open a ticket")
    assert r.text.startswith("Sorry") and "not a valid JSON" in json.loads(stub.chats()[1]["messages"][-1]["content"])["errors"][0]


def test_the_model_asking_for_a_person_hands_over_and_the_bot_stops_answering(bot, stub):
    stub.model = lambda req: call("handoff_to_human", {"reason": "employee is upset about a lost laptop"})
    s = Session()
    r = bot.reply(s, "this is the third time my laptop went missing!!")
    assert r.handoff and r.text == HANDOFF_REPLY and s.state == "handoff" and "laptop" in s.handoff_reason
    before = len(stub.chats())
    r2 = bot.reply(s, "hello? anyone?")
    assert r2.text == WAITING_REPLY and r2.model_calls == 0 and len(stub.chats()) == before
    assert s.messages[-2]["content"] == "hello? anyone?"          # still stored for the person who takes over


def test_plain_words_for_a_person_hand_over_by_rule_without_any_model_call(bot, stub):
    s = Session()
    r = bot.reply(s, "Quero falar com uma pessoa.")
    assert r.handoff and r.model_calls == 0 and stub.requests == [] and "rule" in r.notes[0]


def test_the_turn_limit_hands_over(client, stub):
    b = Bot(client, "chat", max_user_turns=2)
    s = Session()
    b.reply(s, "one")
    b.reply(s, "two")
    r = b.reply(s, "three")
    assert r.handoff and "turn limit" in s.handoff_reason and len(stub.chats()) == 2


def test_a_tool_loop_that_never_ends_is_capped_and_handed_over(client, stub):
    stub.model = lambda req: call("create_ticket", {"product": "x"})
    b = Bot(client, "chat", max_tool_rounds=2)
    s = Session()
    r = b.reply(s, "open a ticket")
    assert r.handoff and "capped at 2" in r.notes[-1] and len(stub.chats()) == 3 and s.state == "handoff"


def test_a_prompt_blocked_by_the_content_filter_is_answered_politely_and_removed_from_history(bot, stub):
    stub.model = lambda req: {"status": 400, "body": {"error": {"code": "content_filter", "message": "filtered", "param": "prompt"}}}
    s = Session(messages=[{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"}])
    r = bot.reply(s, "something the filter dislikes")
    assert r.text == FILTERED_REPLY and "content filter" in r.notes[0] and len(s.messages) == 2


def test_a_completion_cut_by_the_filter_is_replaced_and_not_stored(bot, stub):
    stub.model = lambda req: {"content": "partial text", "finish_reason": "content_filter"}
    s = Session()
    r = bot.reply(s, "hello")
    assert r.text == FILTERED_REPLY and s.messages == []


def test_other_api_errors_roll_the_history_back_and_propagate(client, stub):
    import openai
    stub.model = lambda req: {"status": 400, "body": {"error": {"code": "invalid_request", "message": "bad"}}}
    b = Bot(client, "chat")
    s = Session()
    with pytest.raises(openai.BadRequestError):
        b.reply(s, "hello")
    assert s.messages == []


def test_a_length_cut_is_noted_not_hidden(bot, stub):
    stub.model = lambda req: {"content": "Restart the", "finish_reason": "length"}
    r = bot.reply(Session(), "hello")
    assert r.text == "Restart the" and "cut off" in r.notes[0]


def test_empty_and_oversized_messages_never_reach_the_model(bot, stub):
    with pytest.raises(ValueError):
        bot.reply(Session(), "   ")
    s = Session()
    r = bot.reply(s, "x" * 2001)
    assert "too long" in r.text and s.messages == [] and stub.requests == []


def test_summary_mode_folds_old_turns_with_an_extra_call_and_sends_the_summary_in_the_system_message(client, stub):
    def model(req):
        if not req.get("stream"):                                  # the summariser is not streamed
            return say("Riley Demo, Finance. Asked about Wi-Fi and fans.")
        return say("Fine.")
    stub.model = model
    b = Bot(client, "chat", history_budget=120, keep_last_turns=1)
    s = Session()
    for i in range(5):
        r = b.reply(s, f"question number {i} with some padding words to take up room")
    assert s.summary.startswith("Riley Demo") and s.folded > 0
    last = stub.chats()[-1]
    assert "Riley Demo, Finance" in last["messages"][0]["content"]
    assert all("question number 0" not in m.get("content", "") for m in last["messages"][1:])
    assert any(not c.get("stream") for c in stub.chats()) and r.prompt_tokens > 0
    assert len(s.messages) == 10                                   # the full history is still there for audit


def test_window_mode_drops_old_turns_without_any_summary_call(client, stub):
    b = Bot(client, "chat", memory_mode="window", history_budget=120, keep_last_turns=1)
    s = Session()
    for i in range(5):
        b.reply(s, f"question number {i} with some padding words to take up room")
    assert s.summary == "" and s.folded > 0 and all(c.get("stream") for c in stub.chats())


def test_an_empty_summary_answer_keeps_the_previous_summary(client, stub):
    stub.model = lambda req: {"content": "", "finish_reason": "stop"} if not req.get("stream") else say("ok")
    b = Bot(client, "chat", history_budget=60, keep_last_turns=1)
    s = Session(summary="Alex Demo, VPN problem")
    for i in range(3):
        b.reply(s, f"a long enough question number {i} to need folding")
    assert s.summary == "Alex Demo, VPN problem"


def test_unknown_memory_mode_is_refused(client):
    with pytest.raises(ValueError):
        Bot(client, "chat", memory_mode="forever")
