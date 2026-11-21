import pytest

from llmprobe import budget, stream, tokens


class Clock:
    """Advances 0.1 s per reading, so every timing in the test is exact."""

    def __init__(self):
        self.t = -0.1

    def __call__(self):
        self.t += 0.1
        return round(self.t, 10)


def test_stream_skips_filter_and_usage_chunks_and_reads_usage(client, stub):
    stub.handler = lambda req: {"content": "Ask your manager first", "completion_tokens": 4, "prompt_tokens": 33}
    s = stream.stream_once(client, "chat", [{"role": "user", "content": "q"}], clock=Clock())
    assert s.text == "Ask your manager first"
    assert s.content_chunks == 4 and s.chunks == 8      # filter chunk + role + 4 words + finish + usage
    assert s.completion_tokens == 4 and s.prompt_tokens == 33 and s.finish_reason == "stop"
    j = stub.requests[0]["json"]
    assert j["stream"] is True and j["stream_options"] == {"include_usage": True} and j["max_completion_tokens"] == 300


def test_stream_timing_uses_the_first_content_chunk_not_the_first_chunk(client, stub):
    stub.handler = lambda req: {"content": "a b"}
    s = stream.stream_once(client, "chat", [{"role": "user", "content": "q"}], clock=Clock())
    # readings: start 0.0, filter chunk 0.1, role chunk 0.2, first word 0.3
    assert s.first_chunk_s == pytest.approx(0.1) and s.first_content_s == pytest.approx(0.3)
    assert s.total_s > s.first_content_s


def test_chunks_are_not_tokens(client, stub):
    stub.handler = lambda req: {"content": "one two", "completion_tokens": 9}
    s = stream.stream_once(client, "chat", [{"role": "user", "content": "q"}], clock=Clock())
    assert s.content_chunks == 2 and s.completion_tokens == 9


def test_truncated_stream_reports_length(client, stub):
    stub.handler = lambda req: {"content": "cut", "finish": "length"}
    assert stream.stream_once(client, "chat", [{"role": "user", "content": "q"}], clock=Clock()).finish_reason == "length"


def test_blocking_and_summary(client, stub):
    stub.handler = lambda req: {"content": "a b c"}
    msgs = [{"role": "user", "content": "q"}]
    runs = [stream.stream_once(client, "chat", msgs, clock=Clock()) for _ in range(3)]
    blocks = [stream.blocking_once(client, "chat", msgs, clock=Clock()) for _ in range(3)]
    sm = stream.summarise(runs, blocks)
    assert sm["runs"] == 3 and sm["content_chunks_median"] == 3 and sm["blocking_total_median_s"] == pytest.approx(0.1)
    assert "first content" in stream.render(sm)


def test_plan_arithmetic_and_limits():
    p = budget.make_plan(300_000, 300, 100)
    assert p.available == 299_600
    with pytest.raises(budget.BudgetError, match="32,768"):
        budget.make_plan(300_000, 40_000, 10)
    with pytest.raises(budget.BudgetError, match="1,047,576"):
        budget.make_plan(2_000_000, 300, 10)
    with pytest.raises(budget.BudgetError, match="do not fit"):
        budget.make_plan(1_000, 900, 200)


def test_check_request():
    budget.check_request(300_000, 299_000, 1_000)
    with pytest.raises(budget.BudgetError, match="exceed"):
        budget.check_request(300_000, 299_900, 1_000)
    with pytest.raises(budget.BudgetError, match="maximum output"):
        budget.check_request(1_000_000, 10, 40_000)


def test_split_sections_drops_title_and_comments():
    md = "# Title\n\n<!-- hidden -->\n\n## A\none\n\n## B\ntwo\n"
    assert budget.split_sections(md) == ["## A\none", "## B\ntwo"]


def test_fit_chunks_stops_at_the_first_chunk_that_does_not_fit_keeping_rank_order():
    big = "word " * 60
    chunks = ["small one", big, "small two"]
    kept, dropped = budget.fit_chunks(chunks, 20)
    assert kept == ["small one"] and dropped == [big, "small two"]     # "small two" would fit, but ranks below the dropped one
    assert budget.fit_chunks(chunks, 10_000) == (chunks, [])
    assert budget.fit_chunks(chunks, 1)[0] == []


def test_handbook_sections_have_counted_sizes():
    md = (__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "handbook_leave.md").read_text(encoding="utf-8")
    secs = budget.split_sections(md)
    assert secs[0].startswith("## Annual leave") and len(secs) == 7
    kept, dropped = budget.fit_chunks(secs, 120)
    assert len(kept) == 2 and dropped[0].startswith("## Carry-over")


def test_content_tokens_counts_message_text_only():
    msgs = [{"role": "system", "content": "Tell me"}, {"role": "user", "content": "about the solar system."}]
    assert budget.content_tokens(msgs, "cl100k_base") == tokens.count("Tell me", "cl100k_base") + tokens.count("about the solar system.", "cl100k_base")
