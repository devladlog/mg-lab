"""SLA-breach model: will this purchase request take more than SLA_DAYS to be approved?

A deliberately small model, so that the whole thing can be explained, tested and exported:
  * features known at submission time only (amount, department, category, weekday, month-end), never the outcome;
  * logistic regression (scikit-learn) on a time-ordered split: train on the earlier 75 %, judge on the later 25 %;
  * the fitted model is exported as JSON and as a T-SQL view, so Synapse serverless SQL can score without Python.
The training data in the tests is synthetic. The metrics printed here describe the pipeline, not Contoso.
"""
from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import CATEGORIES, DEPARTMENTS, SLA_DAYS
from .localsql import LocalWarehouse

FEATURES_SQL = """
SELECT RequestId, DepartmentKey, Category, Amount, SubmittedDate, SubmittedWeekday, SlaBreached
FROM gold.FactPurchaseRequest
WHERE Status = 'Approved' AND SlaBreached IS NOT NULL
ORDER BY SubmittedDate, RequestId
"""


def load_training_frame(lake_root) -> pd.DataFrame:
    """Decided, valid requests from the same silver/gold views the warehouse uses."""
    wh = LocalWarehouse(lake_root)
    try:
        df = wh.query(FEATURES_SQL)
    finally:
        wh.close()
    df["SubmittedDate"] = pd.to_datetime(df["SubmittedDate"])
    return df


@dataclass
class FeatureSpec:
    departments: list[str]
    categories: list[str]
    amount_mean: float
    amount_std: float
    month_end_day: int = 25
    late_week_from: int = 4          # Friday, Saturday, Sunday (Monday = 0)

    def names(self) -> list[str]:
        return (["log_amount_z", "late_week", "month_end"]
                + [f"dept={d}" for d in self.departments] + [f"cat={c}" for c in self.categories])


def build_matrix(df: pd.DataFrame, spec: FeatureSpec) -> np.ndarray:
    log_amount = np.log1p(df["Amount"].astype(float).to_numpy())
    cols = [
        (log_amount - spec.amount_mean) / spec.amount_std,
        (df["SubmittedWeekday"].to_numpy() >= spec.late_week_from).astype(float),
        (pd.to_datetime(df["SubmittedDate"]).dt.day.to_numpy() >= spec.month_end_day).astype(float),
    ]
    cols += [(df["DepartmentKey"].to_numpy() == d).astype(float) for d in spec.departments]
    cols += [(df["Category"].to_numpy() == c).astype(float) for c in spec.categories]
    return np.column_stack(cols)


def train(df: pd.DataFrame, train_fraction: float = 0.75, seed: int = 7) -> dict:
    """Fit on the earlier part of the history, evaluate on the later part, return a JSON-serialisable model."""
    df = df.sort_values(["SubmittedDate", "RequestId"]).reset_index(drop=True)
    cut = int(len(df) * train_fraction)
    tr, te = df.iloc[:cut], df.iloc[cut:]
    log_amt = np.log1p(tr["Amount"].astype(float))
    spec = FeatureSpec(sorted(DEPARTMENTS), list(CATEGORIES), float(log_amt.mean()), float(log_amt.std(ddof=0)))
    x_tr, y_tr = build_matrix(tr, spec), tr["SlaBreached"].astype(int).to_numpy()
    x_te, y_te = build_matrix(te, spec), te["SlaBreached"].astype(int).to_numpy()
    clf = LogisticRegression(C=1.0, max_iter=1000, random_state=seed).fit(x_tr, y_tr)
    p = clf.predict_proba(x_te)[:, 1]
    base_rate = float(y_tr.mean())
    metrics = {
        "rows_train": int(len(tr)), "rows_test": int(len(te)),
        "breach_rate_train": round(base_rate, 4), "breach_rate_test": round(float(y_te.mean()), 4),
        "auc_test": round(float(roc_auc_score(y_te, p)), 4),
        "brier_test": round(float(brier_score_loss(y_te, p)), 4),
        "brier_baseline_constant": round(float(brier_score_loss(y_te, np.full(len(te), base_rate))), 4),
    }
    digest = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes()).hexdigest()
    return {
        "model_version": "sla-breach-lr-" + digest[:8],
        "sla_days": SLA_DAYS,
        "library": f"scikit-learn {sklearn.__version__}",
        "training_window": [str(tr["SubmittedDate"].min().date()), str(tr["SubmittedDate"].max().date())],
        "test_window": [str(te["SubmittedDate"].min().date()), str(te["SubmittedDate"].max().date())],
        "data_sha256": digest,
        "spec": {"departments": spec.departments, "categories": spec.categories, "amount_mean": spec.amount_mean,
                 "amount_std": spec.amount_std, "month_end_day": spec.month_end_day, "late_week_from": spec.late_week_from},
        "intercept": float(clf.intercept_[0]),
        "coefficients": dict(zip(spec.names(), (float(c) for c in clf.coef_[0]))),
        "metrics": metrics,
    }


def predict(model: dict, df: pd.DataFrame) -> np.ndarray:
    """Probability of an SLA breach, computed from the exported JSON only (no scikit-learn object needed)."""
    spec = FeatureSpec(**model["spec"])
    x = build_matrix(df, spec)
    w = np.array([model["coefficients"][n] for n in spec.names()])
    return 1.0 / (1.0 + np.exp(-(model["intercept"] + x @ w)))


def _num(v: float) -> str:
    return repr(float(v))


def export_sql(model: dict) -> str:
    """A `gold.RequestRiskScore` view that applies the model inside Synapse serverless SQL."""
    s, c = model["spec"], model["coefficients"]
    dept = " ".join(f"WHEN '{d}' THEN {_num(c['dept=' + d])}" for d in s["departments"])
    cat = " ".join(f"WHEN '{k}' THEN {_num(c['cat=' + k])}" for k in s["categories"])
    return f"""-- Generated by `python -m analytics export-sql` from model {model['model_version']}. Do not edit by hand.
-- Logistic regression exported as arithmetic: serverless SQL pool needs no Python and no model host to score.
-- Trained on {model['training_window'][0]} .. {model['training_window'][1]}; holdout AUC {model['metrics']['auc_test']}.
CREATE OR ALTER VIEW gold.RequestRiskScore AS
WITH f AS (
    SELECT RequestId, DepartmentKey, Category, Status, CAST(Amount AS float) AS Amount, SubmittedWeekday,
           DAY(SubmittedDate) AS SubmittedDay
    FROM gold.FactPurchaseRequest
),
z AS (
    SELECT RequestId, Status,
           {_num(model['intercept'])}
           + {_num(c['log_amount_z'])} * ((LOG(1.0 + Amount) - {_num(s['amount_mean'])}) / {_num(s['amount_std'])})
           + {_num(c['late_week'])} * (CASE WHEN SubmittedWeekday >= {s['late_week_from']} THEN 1.0 ELSE 0.0 END)
           + {_num(c['month_end'])} * (CASE WHEN SubmittedDay >= {s['month_end_day']} THEN 1.0 ELSE 0.0 END)
           + (CASE DepartmentKey {dept} ELSE 0.0 END)
           + (CASE Category {cat} ELSE 0.0 END) AS Logit
    FROM f
)
SELECT RequestId, Status,
       CAST(1.0 / (1.0 + EXP(-Logit)) AS decimal(9, 6)) AS BreachProbability,
       '{model['model_version']}' AS ModelVersion
FROM z;
GO
"""


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population stability index of `actual` against `expected` (bins are the deciles of `expected`).

    Common rule of thumb (an industry convention, not a Microsoft threshold): < 0.1 stable, 0.1-0.25 watch, > 0.25 shifted.
    """
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def save(model: dict, path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh, indent=2)
        fh.write("\n")


def load(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


__all__ = ["load_training_frame", "train", "predict", "export_sql", "psi", "save", "load"]
