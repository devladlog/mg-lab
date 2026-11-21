import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from analytics import CATEGORIES, DEPARTMENTS, SLA_DAYS, ml
from analytics.localsql import LocalWarehouse

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def frame(lake):
    return ml.load_training_frame(lake)


@pytest.fixture(scope="module")
def model(frame):
    return ml.train(frame)


def test_training_frame_comes_from_the_gold_view_decided_and_valid_only(frame):
    assert len(frame) > 800
    assert not set(frame["RequestId"]) & {9001, 9002, 9003, 9004}
    assert frame["SlaBreached"].isin([0, 1]).all()


def test_no_feature_knows_the_outcome(model):
    names = " ".join(model["coefficients"]).lower()
    for leak in ("cycle", "approved", "decided", "sla", "status"):
        assert leak not in names, f"feature name mentions {leak}"
    assert set(model["coefficients"]) == set(ml.FeatureSpec(**model["spec"]).names())


def test_split_is_by_time_so_the_model_never_sees_the_future(model):
    assert model["training_window"][1] < model["test_window"][0] or model["training_window"][1] == model["test_window"][0]
    assert model["metrics"]["rows_train"] > model["metrics"]["rows_test"] > 100


def test_model_beats_the_constant_baseline_on_the_holdout(model):
    m = model["metrics"]
    assert m["auc_test"] > 0.7
    assert m["brier_test"] < m["brier_baseline_constant"]


def test_training_is_reproducible(frame, model):
    again = ml.train(frame)
    assert again["model_version"] == model["model_version"]
    assert again["coefficients"] == pytest.approx(model["coefficients"])


def test_exported_json_alone_reproduces_the_scores(frame, model):
    scores = ml.predict(model, frame)
    assert ((scores > 0) & (scores < 1)).all()
    # higher amount, same everything else, never lowers the risk (the amount coefficient is positive)
    bigger = frame.assign(Amount=frame["Amount"] * 3)
    assert (ml.predict(model, bigger) >= scores - 1e-12).all()


def test_tsql_scoring_view_matches_python_to_six_decimals(lake, tmp_path, frame, model):
    sql = tmp_path / "050-risk-score.sql"
    sql.write_text(ml.export_sql(model), encoding="utf-8")
    wh = LocalWarehouse(lake, extra_files=(sql,))
    try:
        got = wh.query("SELECT RequestId, BreachProbability FROM gold.RequestRiskScore").set_index("RequestId")["BreachProbability"]
        every = wh.query("SELECT * FROM gold.FactPurchaseRequest")
    finally:
        wh.close()
    every["SubmittedDate"] = pd.to_datetime(every["SubmittedDate"])
    want = pd.Series(ml.predict(model, every), index=every["RequestId"])
    both = pd.concat([got.astype(float), want], axis=1, keys=["sql", "py"]).dropna()
    assert len(both) == len(every)
    assert (both["sql"] - both["py"]).abs().max() < 1e-6


def test_committed_sql_is_exactly_what_the_committed_model_exports():
    model = ml.load(ROOT / "model" / "sample-model.json")
    committed = (ROOT / "sql" / "synapse" / "050-risk-score.sql").read_text(encoding="utf-8")
    assert committed == ml.export_sql(model)
    assert model["sla_days"] == SLA_DAYS
    assert set(model["spec"]["departments"]) == set(DEPARTMENTS) and set(model["spec"]["categories"]) == set(CATEGORIES)


def test_model_card_fields_are_present(model):
    for key in ("model_version", "library", "training_window", "test_window", "data_sha256", "metrics", "sla_days"):
        assert key in model
    json.dumps(model)  # serialisable


def test_psi_is_zero_for_the_same_data_and_large_when_amounts_double():
    rng = np.random.default_rng(1)
    base = np.exp(rng.normal(7, 1, 5000))
    assert ml.psi(base, base) == pytest.approx(0.0, abs=1e-9)
    same_dist = np.exp(rng.normal(7, 1, 5000))
    assert ml.psi(base, same_dist) < 0.1
    assert ml.psi(base, base * 2.0) > 0.25


def test_psi_on_the_synthetic_history_is_stable(frame, model):
    cut = pd.Timestamp(model["training_window"][1])
    old, new = frame[frame["SubmittedDate"] <= cut], frame[frame["SubmittedDate"] > cut]
    assert ml.psi(old["Amount"].to_numpy(float), new["Amount"].to_numpy(float)) < 0.1
