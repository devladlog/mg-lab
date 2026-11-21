import math
import random

import pytest

from hrmon import drift
from hrmon.features import input_features, language_hint, length_bucket


def test_identical_windows_have_zero_drift():
    vals = ["leave"] * 20 + ["payroll"] * 20
    r = drift.compare("category", vals, list(vals))
    assert r.psi == pytest.approx(0, abs=1e-12) and r.js == pytest.approx(0, abs=1e-6) and r.status == "ok"


def test_psi_matches_the_formula():
    p, q = [0.5, 0.5], [0.8, 0.2]
    expected = (0.8 - 0.5) * math.log(0.8 / 0.5) + (0.2 - 0.5) * math.log(0.2 / 0.5)
    assert drift.psi(p, q) == pytest.approx(expected) == pytest.approx(0.416, abs=1e-3)


def test_js_distance_is_symmetric_and_bounded():
    p, q = [0.9, 0.1, 1e-9], [1e-9, 0.1, 0.9]
    assert drift.js_distance(p, q) == pytest.approx(drift.js_distance(q, p))
    assert 0 < drift.js_distance(p, q) <= 1


def test_a_brand_new_category_stays_finite_thanks_to_smoothing():
    base = ["en"] * 40
    cur = ["en"] * 26 + ["pt"] * 14                  # "pt" never seen in the baseline
    r = drift.compare("lang", base, cur)
    assert math.isfinite(r.psi) and r.status == "significant"
    assert r.shifts[0][0] in ("pt", "en") and r.shifts[0][2] != r.shifts[0][1]


def test_bands_follow_learn_guidance():
    base = ["a"] * 50 + ["b"] * 50
    assert drift.compare("x", base, ["a"] * 52 + ["b"] * 48).status == "ok"
    assert drift.compare("x", base, ["a"] * 66 + ["b"] * 34).status == "moderate"       # PSI ~0.10-0.2
    assert drift.compare("x", base, ["a"] * 75 + ["b"] * 25).status == "significant"


def test_small_windows_are_insufficient_not_a_verdict():
    r = drift.compare("x", ["a"] * 10, ["b"] * 10)
    assert r.status == "insufficient" and r.psi is None and not r.drifted


def test_same_population_split_in_two_is_not_zero_but_below_threshold():
    """Two samples of the same population differ by chance: that's why we need a threshold and a minimum n."""
    rng = random.Random(7)
    population = rng.choices(["leave", "payroll", "benefits", "equipment"], weights=[4, 3, 2, 1], k=400)
    r = drift.compare("category", population[:200], population[200:])
    assert 0 < r.psi < drift.PSI_MODERATE


def test_empty_distribution_is_rejected():
    with pytest.raises(ValueError):
        drift.distribution({}, ["a"])


@pytest.mark.parametrize("text, lang", [
    ("How many days of annual leave can I carry over?", "en"),
    ("Quantos dias de férias posso gozar seguidos?", "pt"),
    ("O meu recibo de novembro não tem o subsídio de trabalho híbrido.", "pt"),
    ("Can I use the hybrid allowance to buy an office chair?", "en"),
    ("12345", "other"),
])
def test_language_hint(text, lang):
    assert language_hint(text) == lang


def test_length_buckets_and_features_never_include_the_text():
    assert [length_bucket("x" * n) for n in (10, 60, 150, 250)] == ["<60", "60-119", "120-199", "200+"]
    f = input_features("Onde vejo o meu recibo de vencimento de outubro?")
    assert f == {"lang": "pt", "length": "<60"}


def test_the_repo_datasets_really_shift_language():
    import json
    from pathlib import Path
    data = Path(__file__).resolve().parents[1] / "data"
    load = lambda n: [json.loads(x)["question"] for x in (data / n).read_text(encoding="utf-8").splitlines()]
    base, cur = load("baseline.jsonl"), load("current.jsonl")
    assert len(base) == len(cur) == 40
    pt_base = sum(language_hint(q) == "pt" for q in base)
    pt_cur = sum(language_hint(q) == "pt" for q in cur)
    assert pt_base <= 4 and pt_cur >= 10
