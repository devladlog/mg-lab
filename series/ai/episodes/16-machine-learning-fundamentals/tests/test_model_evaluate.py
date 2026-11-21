import numpy as np
import pandas as pd
import pytest

from mlbasics import evaluate, model
from mlbasics.data import AVAILABLE_AT_OPEN, GROUP, TARGET


def test_pipeline_learns_scaling_from_training_rows_only():
    tr = pd.DataFrame({"queue_backlog": [1.0, 2.0, 3.0], "priority": ["P1", "P2", "P1"]})
    pipe = model.build("logistic", ["queue_backlog", "priority"])
    pipe.fit(tr, [0, 1, 0])
    scaler = pipe.named_steps["pre"].named_transformers_["num"].named_steps["scale"]
    assert scaler.mean_[0] == pytest.approx(2.0)          # the training mean, whatever the test rows look like
    unseen = pd.DataFrame({"queue_backlog": [1000.0], "priority": ["P9"]})
    assert pipe.predict_proba(unseen).shape == (1, 2)      # unknown category: handle_unknown="ignore"


def test_columns_split_into_categorical_and_numeric():
    cat, num = model.columns_for(AVAILABLE_AT_OPEN + [GROUP])
    assert "priority" in cat and GROUP in cat and "queue_backlog" in num and "is_vip" in num


def test_unknown_model_kind():
    with pytest.raises(ValueError):
        model.build("magic", AVAILABLE_AT_OPEN)


def test_dummy_scores_the_prevalence_and_loses_to_nothing_on_accuracy(df):
    d = df.iloc[:3000]
    m = model.build("dummy", AVAILABLE_AT_OPEN).fit(d[AVAILABLE_AT_OPEN], d[TARGET])
    p = m.predict_proba(d[AVAILABLE_AT_OPEN])[:, 1]
    s = evaluate.scores(d[TARGET], p)
    assert s["roc_auc"] == 0.5 and s["avg_precision"] == pytest.approx(d[TARGET].mean())
    assert s["accuracy"] == pytest.approx(1 - d[TARGET].mean())


def test_scores_on_known_arrays():
    y = np.array([0, 0, 1, 1])
    perfect = evaluate.scores(y, [0.1, 0.2, 0.8, 0.9])
    assert perfect["roc_auc"] == 1.0 and perfect["avg_precision"] == 1.0 and perfect["accuracy"] == 1.0
    assert evaluate.scores(y, [0.9, 0.8, 0.2, 0.1])["roc_auc"] == 0.0


def test_accuracy_paradox_on_a_rare_class():
    y = np.array([1] * 5 + [0] * 95)
    assert evaluate.scores(y, np.zeros(100))["accuracy"] == pytest.approx(0.95)
    assert evaluate.confusion(y, np.zeros(100), 0.5)["recall"] == 0.0


def test_confusion_and_cost():
    y, p = np.array([1, 1, 0, 0, 0]), np.array([0.9, 0.2, 0.8, 0.1, 0.1])
    c = evaluate.confusion(y, p, 0.5)
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (1, 1, 1, 2)
    assert evaluate.cost(y, p, 0.5, cost_fn=10, cost_fp=1) == 11


def test_threshold_moves_down_when_a_miss_costs_more():
    rng = np.random.default_rng(0)
    y = (rng.random(2000) < 0.1).astype(int)
    p = np.clip(0.1 + 0.4 * y + rng.normal(0, 0.15, 2000), 0.001, 0.999)
    t_equal = evaluate.choose_threshold(y, p, 1, 1)
    t_miss = evaluate.choose_threshold(y, p, 10, 1)
    assert t_miss < t_equal
    assert evaluate.cost(y, p, t_miss, 10, 1) <= evaluate.cost(y, p, 0.5, 10, 1)


def test_reference_costs():
    assert evaluate.reference_costs([1, 1, 0, 0, 0], 10, 1) == {"flag_nothing": 20.0, "flag_everything": 3.0}
