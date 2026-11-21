"""Look at the data before any model: class balance, missing values, repeat requesters, and a leakage scan."""
from __future__ import annotations

import pandas as pd
from sklearn.metrics import roc_auc_score

from .data import AVAILABLE_AT_OPEN, GROUP, TARGET


def class_balance(df: pd.DataFrame) -> dict:
    pos = int(df[TARGET].sum())
    return {"rows": len(df), "positives": pos, "prevalence": pos / len(df),
            # the accuracy of a "model" that always predicts the majority class
            "majority_accuracy": max(pos, len(df) - pos) / len(df)}


def missing(df: pd.DataFrame) -> dict[str, float]:
    m = df.isna().mean()
    return {c: float(v) for c, v in m.items() if v > 0}


def repeat_requesters(df: pd.DataFrame) -> dict:
    sizes = df.groupby(GROUP).size()
    return {"requesters": int(sizes.size), "median_tickets": float(sizes.median()), "max_tickets": int(sizes.max())}


def single_feature_auc(df: pd.DataFrame, column: str) -> float:
    """How well ONE column alone ranks the target (0.5 = no signal, 1.0 = perfect), direction ignored.
    Categoricals are scored with the positive rate of the category (computed on the same rows: this is a scan, not a model)."""
    y = df[TARGET].to_numpy()
    s = df[column]
    if s.dtype == object or str(s.dtype).startswith("str") or str(s.dtype) == "category":
        s = s.map(df.groupby(column)[TARGET].mean())
    x = s.fillna(s.median()).to_numpy(dtype=float)
    a = roc_auc_score(y, x)
    return float(max(a, 1 - a))


def leakage_scan(df: pd.DataFrame, threshold: float = 0.95) -> list[dict]:
    """Two independent warnings: (1) a column a dispatcher cannot know at prediction time, (2) a single column that is
    almost a copy of the answer. Either one alone is a reason to stop and ask where the column comes from."""
    rows = []
    for c in df.columns:
        if c in (TARGET, GROUP) or c == "opened_day":
            continue
        auc = single_feature_auc(df, c)
        not_at_open = c not in AVAILABLE_AT_OPEN
        rows.append({"column": c, "auc": auc, "not_available_at_open": not_at_open,
                     "suspect": not_at_open or auc >= threshold})
    return sorted(rows, key=lambda r: -r["auc"])


def render(df: pd.DataFrame, threshold: float = 0.95) -> str:
    b = class_balance(df)
    lines = [f"rows {b['rows']:,}   positives {b['positives']:,} ({b['prevalence']:.1%})   "
             f"always-predict-no accuracy {b['majority_accuracy']:.1%}",
             f"requesters {repeat_requesters(df)['requesters']}, median tickets each {repeat_requesters(df)['median_tickets']:.0f}",
             f"missing values: {missing(df) or 'none'}", "", f"{'column':<24}{'single-column AUC':>18}  note"]
    for r in leakage_scan(df, threshold):
        note = "SUSPECT: " + ("not known when the ticket arrives" if r["not_available_at_open"] else f"AUC >= {threshold}") if r["suspect"] else ""
        lines.append(f"{r['column']:<24}{r['auc']:>18.3f}  {note}")
    return "\n".join(lines)


def assert_no_leak(columns: list[str]) -> None:
    bad = [c for c in columns if c not in AVAILABLE_AT_OPEN]
    if bad:
        raise ValueError(f"columns not available when the ticket arrives: {bad}")


__all__ = ["class_balance", "missing", "repeat_requesters", "single_feature_auc", "leakage_scan", "render", "assert_no_leak"]
