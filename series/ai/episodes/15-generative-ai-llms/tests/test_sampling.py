import itertools

import pytest

from llmprobe import sampling
from llmprobe.sampling import Setting

FACTS = [r"\b5\b", "31 March"]


def test_similarity_bounds():
    assert sampling.similarity("abc", "abc") == 1.0
    assert sampling.similarity("abc", "xyz") == 0.0
    assert sampling.mean_similarity(["only one"]) == 1.0


def test_facts_present_needs_all_facts():
    assert sampling.facts_present("You can carry 5 days until 31 March.", FACTS)
    assert not sampling.facts_present("You can carry 5 days.", FACTS)
    assert not sampling.facts_present("Up to 15 days until 31 March.", FACTS)   # \b5\b must not match inside 15


def test_labels():
    assert Setting(0, None).label == "t=0 no seed"
    assert Setting(1, 42).label == "t=1 seed=42"


def test_run_setting_sends_temperature_and_seed_only_when_set(client, stub):
    msgs = [{"role": "user", "content": "q"}]
    sampling.run_setting(client, "chat", msgs, Setting(0, None), runs=1)
    sampling.run_setting(client, "chat", msgs, Setting(1, 42), runs=1)
    a, b = (r["json"] for r in stub.requests)
    assert a["temperature"] == 0 and "seed" not in a
    assert b["temperature"] == 1 and b["seed"] == 42
    assert a["max_completion_tokens"] == 200


def test_summarise_counts_distinct_facts_and_fingerprints(client, stub):
    answers = itertools.cycle(["Carry 5 days until 31 March.", "Carry 5 days until 31 March.", "You may carry some days over."])
    fps = itertools.cycle(["fp_a", "fp_a", "fp_b"])
    stub.handler = lambda req: {"content": next(answers), "fingerprint": next(fps)}
    res = sampling.run_setting(client, "chat", [{"role": "user", "content": "q"}], Setting(1, None), runs=3)
    s = sampling.summarise(res, FACTS)
    assert s["runs"] == 3 and s["distinct"] == 2
    assert s["fact_rate"] == pytest.approx(2 / 3)
    assert s["fingerprints"] == ["fp_a", "fp_b"]
    assert 0 < s["mean_similarity"] < 1


def test_failing_reports_lost_facts_and_truncation():
    ok = {"label": "t=0", "fact_rate": 1.0, "truncated": 0}
    bad = {"label": "t=1", "fact_rate": 0.75, "truncated": 2}
    assert sampling.failing([ok]) == []
    why = sampling.failing([ok, bad])
    assert len(why) == 2 and "75%" in why[0] and "cut off" in why[1]
    assert sampling.failing([bad], min_fact_rate=0.5) == ["t=1: 2 answer(s) cut off by max_completion_tokens"]


def test_render_lists_every_setting(client, stub):
    stub.handler = lambda req: {"content": "Carry 5 days until 31 March."}
    rs = [sampling.summarise(sampling.run_setting(client, "chat", [{"role": "user", "content": "q"}], s, 2), FACTS)
          for s in sampling.DEFAULT_SETTINGS]
    out = sampling.render(rs)
    assert all(s.label in out for s in sampling.DEFAULT_SETTINGS) and "fp_test" in out
