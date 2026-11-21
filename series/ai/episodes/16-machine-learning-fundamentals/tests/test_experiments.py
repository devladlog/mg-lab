import pytest

from mlbasics import experiments, splits
from mlbasics.data import AVAILABLE_AT_OPEN, GROUP, TARGET


def test_leaky_column_makes_the_model_look_brilliant(protocol_rows):
    leaky = protocol_rows["random + leaky column"]["logistic"]["avg_precision"]
    honest = protocol_rows["group split, no id"]["logistic"]["avg_precision"]
    assert leaky > 0.9 and honest < 0.5


def test_sharing_people_between_train_and_test_inflates_the_score(protocol_rows):
    shared = protocol_rows["random + requester id"]
    new_people = protocol_rows["group split (new people)"]
    assert shared["shared_requesters"] > 100 and new_people["shared_requesters"] == 0
    assert shared["logistic"]["avg_precision"] > new_people["logistic"]["avg_precision"] + 0.03


def test_group_protocols_have_no_shared_people_and_time_split_has_some(protocol_rows):
    assert protocol_rows["group split, no id"]["shared_requesters"] == 0
    assert protocol_rows["time split (later days)"]["shared_requesters"] > 0


def test_every_honest_protocol_beats_no_skill_but_not_by_much(protocol_rows):
    for name in ("group split (new people)", "group split, no id", "time split (later days)"):
        r = protocol_rows[name]
        assert r["logistic"]["avg_precision"] > 1.5 * r["prevalence"] and r["logistic"]["roc_auc"] < 0.85


def test_baseline_accuracy_hides_a_useless_model(df):
    b = experiments.baseline(df)
    assert b["dummy"]["accuracy"] > 0.8 and b["dummy"]["roc_auc"] == 0.5
    assert b["logistic"]["accuracy"] - b["dummy"]["accuracy"] < 0.02       # accuracy barely moves...
    assert b["logistic"]["avg_precision"] > 1.5 * b["dummy"]["avg_precision"]   # ...while ranking skill is real


def test_deep_trees_memorise(depth_rows):
    by = {r["max_depth"]: r for r in depth_rows}
    assert by[None]["train"] == pytest.approx(1.0) and by[None]["train"] - by[None]["validation"] > 0.5
    best = max(depth_rows, key=lambda r: r["validation"])
    assert best["max_depth"] not in (None, 1) and best["validation"] > by[None]["validation"] + 0.05
    assert [r["train"] for r in depth_rows] == sorted(r["train"] for r in depth_rows)   # training score only goes up


def test_select_model_uses_out_of_fold_predictions_and_sorts(small):
    tr, _ = splits.group_split(small)
    ranked = experiments.select_model(tr, AVAILABLE_AT_OPEN, folds=3, candidates=(("logistic", {"C": 0.1}), ("logistic", {"C": 1.0})))
    assert len(ranked) == 2 and len(ranked[0]["oof"]) == len(tr)
    assert ranked[0]["cv_avg_precision"] >= ranked[1]["cv_avg_precision"]


def test_train_and_test_never_shares_people_and_excludes_identifiers(trained):
    assert GROUP not in trained["features"] and "first_response_minutes" not in trained["features"]
    assert trained["rows"]["train_requesters"] + trained["rows"]["test_requesters"] == 500
    assert 0 < trained["threshold"] < 0.5          # a missed breach costs 10x a false alarm: lower than the default 0.5


def test_trained_model_beats_doing_nothing(trained):
    ok, why = experiments.verdict(trained)
    assert ok, why
    assert trained["cost_model"] < min(trained["cost_reference"].values())
    c = trained["confusion"]
    assert c["recall"] > 0.6 and c["precision"] < 0.5          # many false alarms is the price of catching most breaches


def test_verdict_reasons():
    base = {"cost_model": 100, "cost_reference": {"flag_nothing": 90, "flag_everything": 120}, "test": {"avg_precision": 0.15, "prevalence": 0.1}}
    ok, why = experiments.verdict(base)
    assert not ok and len(why) == 2 and "not below" in why[0] and "1.50x" in why[1]
    assert experiments.verdict({**base, "cost_model": 50, "test": {"avg_precision": 0.4, "prevalence": 0.1}})[0]
