import math

import pytest
from conftest import lp

from llmprobe import probe


def resp_with(client, stub, first):
    stub.handler = lambda req: {"content": first["token"], "logprobs": {"content": [first], "refusal": None}}
    return client.chat.completions.create(model="chat", messages=[{"role": "user", "content": "x"}])


def test_candidates_are_probabilities_and_variants_merge(client, stub):
    first = lp("C", math.log(0.60), [("C", math.log(0.50)), (" C", math.log(0.10)), ("B", math.log(0.30)), ("D", math.log(0.05)), ("A", math.log(0.04))])
    s = probe.step_from_response(resp_with(client, stub, first))
    assert s.candidates[0].token == "C" and s.candidates[0].prob == pytest.approx(0.60)   # "C" and " C" merged
    assert [c.token for c in s.candidates] == ["C", "B", "D", "A"]
    assert s.mass == pytest.approx(0.99)
    assert s.answer == "C"


def test_letter_with_bracket_is_the_same_answer(client, stub):
    first = lp("C", math.log(0.7), [("C", math.log(0.6)), ("C)", math.log(0.1)), ("B", math.log(0.3))])
    s = probe.step_from_response(resp_with(client, stub, first))
    assert s.candidates[0].token == "C" and s.candidates[0].prob == pytest.approx(0.7)


def test_entropy_is_zero_when_sure_and_grows_when_not(client, stub):
    sure = probe.step_from_response(resp_with(client, stub, lp("B", -0.0001, [("B", -0.0001)])))
    unsure = probe.step_from_response(resp_with(client, stub, lp("A", math.log(0.5), [("A", math.log(0.5)), ("B", math.log(0.5))])))
    assert sure.entropy_bits == pytest.approx(0.0, abs=1e-9)
    assert unsure.entropy_bits == pytest.approx(1.0)


def test_missing_logprobs_is_an_error(client, stub):
    stub.handler = lambda req: {"content": "C"}
    r = client.chat.completions.create(model="chat", messages=[{"role": "user", "content": "x"}])
    with pytest.raises(probe.ProbeError, match="no logprobs"):
        probe.step_from_response(r)


def test_whitespace_only_first_token_is_an_error(client, stub):
    with pytest.raises(probe.ProbeError):
        probe.step_from_response(resp_with(client, stub, lp(" ", -0.1, [(" ", -0.1), ("\n", -2.0)])))


def test_request_shape(client, stub):
    stub.handler = lambda req: {"content": "B", "logprobs": {"content": [lp("B", -0.1, [("B", -0.1)])], "refusal": None}}
    probe.ask(client, "chat", "Capital?", {"A": "Porto", "B": "Lisbon"}, context="Some policy.", top=5)
    req = stub.requests[0]
    assert req["path"].endswith("/chat/completions") and req["auth"] == "Bearer fake-entra-token"
    j = req["json"]
    assert j["model"] == "chat" and j["logprobs"] is True and j["top_logprobs"] == 5 and j["temperature"] == 0
    assert j["max_completion_tokens"] == 3 and "max_tokens" not in j
    user = j["messages"][1]["content"]
    assert "<<CONTEXT>>\nSome policy.\n<<END>>" in user and "A) Porto" in user and user.endswith("Answer:")


def test_no_context_means_no_delimiters():
    m = probe.build_messages("Q?", {"A": "x"}, None)
    assert "<<CONTEXT>>" not in m[1]["content"]


@pytest.mark.parametrize("top", [0, 21])
def test_top_logprobs_limit_is_zero_to_twenty_and_we_need_at_least_one(top):
    with pytest.raises(probe.ProbeError):
        probe.request_args(top)


def test_decision_threshold():
    cands = lambda p: (probe.Candidate("A", p), probe.Candidate("B", 1 - p))  # noqa: E731
    assert probe.decide(probe.Step("A", 0.95, cands(0.95), 1.0, 0.3)) == "answer"
    assert probe.decide(probe.Step("A", 0.6, cands(0.6), 1.0, 0.9)) == "escalate"


def test_run_cases_asks_each_case_twice_and_scores(client, stub):
    calls = []

    def handler(req):
        user = req["messages"][1]["content"]
        calls.append("<<CONTEXT>>" in user)
        p = 0.97 if "<<CONTEXT>>" in user else 0.55
        return {"content": "C", "logprobs": {"content": [lp("C", math.log(p), [("C", math.log(p)), ("B", math.log(1 - p))])], "refusal": None}}

    stub.handler = handler
    cases = [{"id": "days", "question": "Days?", "options": {"A": "20", "B": "22", "C": "25"}, "correct": "C"}]
    rows = probe.run_cases(client, "chat", cases, "context text", top=5, threshold=0.9)
    assert calls == [False, True]
    assert [r["decision"] for r in rows] == ["escalate", "answer"] and all(r["correct"] for r in rows)
    assert "days" in probe.render(rows)
