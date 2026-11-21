import json

import pytest
from conftest import oracle

from fttriage import evaluate
from fttriage.labels import Label
from fttriage.prompts import SHORT_SYSTEM, baseline_system


@pytest.fixture
def cases(data):
    _, golden, sp = data
    return sp.test + golden            # 29 labelled + 16 category-only


def test_wilson_interval_is_honest_about_small_samples():
    lo, hi = evaluate.wilson(27, 30)
    assert lo == pytest.approx(0.744, abs=0.005) and hi == pytest.approx(0.965, abs=0.005)
    assert evaluate.wilson(0, 0) == (0.0, 0.0)
    lo, hi = evaluate.wilson(30, 30)
    assert hi == 1.0 and lo < 0.9


def test_sign_test_exact():
    assert evaluate.sign_test(0, 0) == 1.0
    assert evaluate.sign_test(5, 5) == 1.0
    assert evaluate.sign_test(0, 5) == pytest.approx(2 / 32)
    assert evaluate.sign_test(1, 6) == pytest.approx(2 * (1 + 7) / 128)


def test_label_parsing_rules():
    from fttriage.labels import parse_label
    good = '{"category":"leave","urgency":"low","needs_human":false}'
    assert parse_label(good) == Label("leave", "low", False)
    assert parse_label("```json\n" + good + "\n```") == Label("leave", "low", False)
    for bad in (None, "", "leave", "Sure! " + good, '{"category":"leave"}', '[1]',
                '{"category":"holiday","urgency":"low","needs_human":false}',
                '{"category":"leave","urgency":"low","needs_human":"no"}',
                '{"category":"leave","urgency":"low","needs_human":false,"why":"x"}'):
        assert parse_label(bad) is None, bad


def test_run_sends_the_right_system_prompt_and_measures_what_the_service_billed(stub, client, cases):
    stub.behaviours["base"] = oracle(cases)
    stub.behaviours["triage-ft"] = oracle(cases)
    base = evaluate.run(client, "base", baseline_system(), cases)
    tuned = evaluate.run(client, "triage-ft", SHORT_SYSTEM, cases)
    sent = [json.loads(r["body"]) for r in stub.requests if r["path"].endswith("/chat/completions")]
    assert sent[0]["messages"][0]["content"] == baseline_system()
    assert sent[-1]["messages"][0]["content"] == SHORT_SYSTEM
    assert sent[0]["temperature"] == 0 and "response_format" not in sent[0]
    assert base[0].prompt_tokens > 10 * tuned[0].prompt_tokens


def test_metrics_with_perfect_answers(stub, client, cases):
    stub.behaviours["m"] = oracle(cases)
    m = evaluate.metrics(evaluate.run(client, "m", SHORT_SYSTEM, cases))
    assert m.n == 45 and m.format_ok == 1 and m.category_acc == 1 and m.exact == 1 and m.needs_human_recall == 1
    assert m.wrong_by_category == {}
    assert m.urgency_acc == 1                                   # graded only on the 29 items that carry an urgency


def test_wrong_and_malformed_answers_are_counted_as_wrong(stub, client, cases):
    ids = [c.id for c in cases]
    stub.behaviours["m"] = oracle(cases, wrong_ids=ids[:3], malformed_ids=ids[10:12])
    m = evaluate.metrics(evaluate.run(client, "m", SHORT_SYSTEM, cases))
    assert m.format_ok == pytest.approx(43 / 45)
    assert m.category_acc == pytest.approx(40 / 45)             # 3 wrong + 2 unparsable (assuming none of them is 'other')
    assert sum(m.wrong_by_category.values()) == 5


def test_a_failed_call_is_recorded_not_raised(stub, client, cases):
    stub.behaviours["m"] = oracle(cases)
    stub.chat_fail_on = cases[0].text
    calls = evaluate.run(client, "m", SHORT_SYSTEM, cases)
    assert calls[0].error and calls[0].label is None and calls[1].label is not None
    assert evaluate.metrics(calls).format_ok < 1


def test_tuned_model_that_is_as_good_and_much_shorter_is_promoted(stub, client, cases):
    ids = [c.id for c in cases]
    stub.behaviours["base"] = oracle(cases, wrong_ids=ids[:4])
    stub.behaviours["triage-ft"] = oracle(cases, wrong_ids=ids[:2])
    cmp = evaluate.compare(evaluate.run(client, "base", baseline_system(), cases),
                           evaluate.run(client, "triage-ft", SHORT_SYSTEM, cases))
    assert cmp.promote and cmp.prompt_saving > 0.9
    assert cmp.only_tuned_right >= cmp.only_base_right and 0 < cmp.p_value <= 1
    text = evaluate.render(cmp)
    assert "PROMOTE" in text and "DO NOT" not in text and "95% interval" in text and "sign test" in text


def test_a_tuned_model_that_is_worse_is_not_promoted_even_if_cheaper(stub, client, cases):
    ids = [c.id for c in cases]
    stub.behaviours["base"] = oracle(cases)
    stub.behaviours["triage-ft"] = oracle(cases, wrong_ids=ids[:6])
    cmp = evaluate.compare(evaluate.run(client, "base", baseline_system(), cases),
                           evaluate.run(client, "triage-ft", SHORT_SYSTEM, cases))
    assert not cmp.promote and not cmp.verdicts["category: not worse than the baseline"] and cmp.verdicts["prompt tokens saved"]
    assert "DO NOT PROMOTE" in evaluate.render(cmp)


def test_missing_sensitive_cases_fails_the_needs_human_gate(stub, client, data):
    _, _, sp = data
    cases = sp.test

    def never_human(user, system):
        e = next(c for c in cases if c.text == user)
        return json.dumps({"category": e.category, "urgency": e.urgency, "needs_human": False})

    stub.behaviours["base"] = oracle(cases)
    stub.behaviours["triage-ft"] = never_human
    cmp = evaluate.compare(evaluate.run(client, "base", baseline_system(), cases),
                           evaluate.run(client, "triage-ft", SHORT_SYSTEM, cases))
    assert cmp.base.category_acc == cmp.tuned.category_acc == 1      # same category accuracy...
    assert not cmp.verdicts["needs_human recall"] and not cmp.promote   # ...but it never escalates: blocked


def test_compare_refuses_different_items(stub, client, cases):
    stub.behaviours["m"] = oracle(cases)
    a = evaluate.run(client, "m", SHORT_SYSTEM, cases)
    with pytest.raises(ValueError):
        evaluate.compare(a, a[:-1])
