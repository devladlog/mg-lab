import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from mlbasics import audit, data, splits
from mlbasics.data import AVAILABLE_AT_OPEN, GROUP, LEAKY, TARGET, TIME


def test_generation_is_deterministic_and_seed_dependent():
    a, b, c = data.generate(n=500, requesters=40), data.generate(n=500, requesters=40), data.generate(n=500, requesters=40, seed=1)
    assert data.fingerprint(a) == data.fingerprint(b) != data.fingerprint(c)
    pd.testing.assert_frame_equal(a, b)


def test_shape_columns_and_planted_pitfalls(df):
    assert len(df) == 8000
    assert set(AVAILABLE_AT_OPEN + LEAKY + [GROUP, TIME, TARGET]) == set(df.columns)
    assert 0.08 < df[TARGET].mean() < 0.18                                  # rare positives
    assert df.groupby(GROUP).size().median() >= 10                          # repeat requesters
    assert df.isna().sum()[lambda s: s > 0].index.tolist() == ["text_length"]
    assert roc_auc_score(df[TARGET], df["first_response_minutes"]) > 0.95   # the leaking column


def test_fictional_values_only(df):
    assert df[GROUP].str.fullmatch(r"E\d{4}").all()
    assert set(df["department"]) <= set(data.DEPARTMENTS) and set(df["language"]) <= {"en", "pt"}


def test_class_balance_and_majority_accuracy(df):
    b = audit.class_balance(df)
    assert b["majority_accuracy"] == pytest.approx(1 - b["prevalence"])
    assert b["majority_accuracy"] > 0.8                                     # the accuracy trap


def test_missing_and_repeat_requesters(df):
    assert list(audit.missing(df)) == ["text_length"]
    r = audit.repeat_requesters(df)
    assert r["requesters"] == df[GROUP].nunique() and r["max_tickets"] >= r["median_tickets"]


def test_leakage_scan_flags_only_the_leaky_column(df):
    scan = audit.leakage_scan(df)
    assert [r["column"] for r in scan if r["suspect"]] == ["first_response_minutes"]
    assert scan[0]["column"] == "first_response_minutes" and scan[0]["auc"] > 0.95
    assert all(r["auc"] < 0.7 for r in scan[1:])


def test_scan_without_the_leaky_column_is_clean(df):
    assert not any(r["suspect"] for r in audit.leakage_scan(df.drop(columns=LEAKY)))


def test_a_copy_of_the_target_is_flagged_even_if_it_looks_available():
    d = pd.DataFrame({"priority": ["P1", "P2"] * 50, "copy": [0, 1] * 50, TARGET: [0, 1] * 50, GROUP: ["E1"] * 100})
    assert {r["column"]: r["suspect"] for r in audit.leakage_scan(d)}["copy"] is True


def test_categorical_single_feature_auc(df):
    assert 0.5 <= audit.single_feature_auc(df, "category") < 0.7


def test_assert_no_leak():
    audit.assert_no_leak(AVAILABLE_AT_OPEN)
    with pytest.raises(ValueError, match="first_response_minutes"):
        audit.assert_no_leak(AVAILABLE_AT_OPEN + LEAKY)


def test_render_mentions_suspect_and_accuracy_trap(df):
    out = audit.render(df)
    assert "SUSPECT" in out and "always-predict-no accuracy" in out


def test_random_split_is_stratified_and_shares_people(df):
    tr, te = splits.random_split(df)
    assert abs(tr[TARGET].mean() - te[TARGET].mean()) < 0.01
    assert splits.overlap(tr, te) > 100 and len(tr) + len(te) == len(df)


def test_group_split_has_no_shared_people(df):
    tr, te = splits.group_split(df)
    assert splits.overlap(tr, te) == 0 and len(tr) + len(te) == len(df)
    assert 0.2 < len(te) / len(df) < 0.3


def test_time_split_only_looks_forward(df):
    tr, te = splits.time_split(df)
    assert tr[TIME].max() < te[TIME].min()
    assert 0.2 < len(te) / len(df) < 0.3


def test_splits_are_reproducible(df):
    a, _ = splits.group_split(df, seed=3)
    b, _ = splits.group_split(df, seed=3)
    assert a.index.equals(b.index) and np.array_equal(a.index, b.index)
