from helpbot import memory
from helpbot.memory import estimate_tokens, plan_context, split_turns


def u(t):
    return {"role": "user", "content": t}


def a(t):
    return {"role": "assistant", "content": t}


def tool_turn():
    return [u("open a ticket"),
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "create_ticket", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok": false}'},
            a("Which product?")]


def test_split_turns_keeps_a_tool_call_with_its_result():
    msgs = [u("hi"), a("hello")] + tool_turn() + [u("bye")]
    turns = split_turns(msgs)
    assert [len(t) for t in turns] == [2, 4, 1]
    assert turns[1][1]["tool_calls"] and turns[1][2]["role"] == "tool"


def test_plan_keeps_everything_when_it_fits():
    msgs = [u("hi"), a("hello"), u("bye"), a("bye")]
    p = plan_context(msgs, "", budget=10_000)
    assert p.to_fold == [] and p.keep == msgs


def test_plan_folds_oldest_whole_turns_first_and_always_keeps_the_newest_two():
    msgs = []
    for i in range(6):
        msgs += [u(f"question {i} " + "x" * 60), a(f"answer {i} " + "y" * 60)]
    p = plan_context(msgs, "", budget=200, keep_last_turns=2)
    assert len(split_turns(p.keep)) >= 2
    assert p.to_fold == msgs[: len(p.to_fold)]                   # a prefix: oldest first
    assert len(p.to_fold) % 2 == 0                               # whole turns only
    assert p.keep[0]["content"].startswith("question")


def test_plan_never_leaves_fewer_than_keep_last_turns_even_over_budget():
    msgs = [u("x" * 3000), a("y" * 3000), u("z" * 3000), a("w" * 3000)]
    p = plan_context(msgs, "", budget=10, keep_last_turns=2)
    assert p.to_fold == [] and len(split_turns(p.keep)) == 2


def test_plan_counts_the_summary_against_the_budget():
    msgs = [u("a" * 90), a("b" * 90), u("c" * 90), a("d" * 90), u("e"), a("f")]
    without = plan_context(msgs, "", budget=250, keep_last_turns=1)
    with_summary = plan_context(msgs, "s" * 450, budget=250, keep_last_turns=1)
    assert len(with_summary.to_fold) > len(without.to_fold)


def test_estimate_is_conservative_for_english_and_counts_tool_arguments():
    assert estimate_tokens("hello world") == 4                   # 11 chars / 3
    m = {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "f", "arguments": "x" * 30}}]}
    assert memory.message_tokens(m) == 4 + estimate_tokens("f" + "x" * 30)


def test_render_transcript_shows_tool_results_and_skips_empty_assistant_messages():
    t = memory.render_transcript(tool_turn())
    assert "employee: open a ticket" in t and "[tool result:" in t and "assistant: Which product?" in t
