"""The experiments of the episode. Every function returns plain data; cli.py prints it."""
from __future__ import annotations

import pandas as pd
from sklearn.model_selection import GroupKFold, cross_val_predict

from . import splits
from .data import AVAILABLE_AT_OPEN, GROUP, LEAKY, TARGET
from .evaluate import average_precision_score, choose_threshold, confusion, cost, reference_costs, scores
from .model import build

PROTOCOLS = {
    "random + leaky column":     (splits.random_split, AVAILABLE_AT_OPEN + [GROUP] + LEAKY),
    "random + requester id":     (splits.random_split, AVAILABLE_AT_OPEN + [GROUP]),
    "group split (new people)":  (splits.group_split, AVAILABLE_AT_OPEN + [GROUP]),
    "group split, no id":        (splits.group_split, AVAILABLE_AT_OPEN),
    "time split (later days)":   (splits.time_split, AVAILABLE_AT_OPEN),
}


def compare_protocols(df: pd.DataFrame, kinds=("logistic", "forest"), seed: int = 0) -> list[dict]:
    """The same model families, evaluated five ways. Only the evaluation changes, never the algorithm."""
    rows = []
    for name, (split, features) in PROTOCOLS.items():
        tr, te = split(df, seed=seed) if split is not splits.time_split else split(df)
        row = {"protocol": name, "train": len(tr), "test": len(te), "shared_requesters": splits.overlap(tr, te),
               "prevalence": float(te[TARGET].mean())}
        for k in kinds:
            m = build(k, features).fit(tr[features], tr[TARGET])
            p = m.predict_proba(te[features])[:, 1]
            s = scores(te[TARGET], p)
            row[k] = {"avg_precision": s["avg_precision"], "roc_auc": s["roc_auc"]}
        rows.append(row)
    return rows


def baseline(df: pd.DataFrame, seed: int = 0) -> dict:
    """Accuracy of 'predict no breach' versus what a real model and a dummy score on the same held-out requesters."""
    tr, te = splits.group_split(df, seed=seed)
    out = {}
    for kind in ("dummy", "logistic"):
        m = build(kind, AVAILABLE_AT_OPEN).fit(tr[AVAILABLE_AT_OPEN], tr[TARGET])
        p = m.predict_proba(te[AVAILABLE_AT_OPEN])[:, 1]
        out[kind] = scores(te[TARGET], p)
    return out


def depth_curve(df: pd.DataFrame, depths=(1, 2, 3, 5, 8, 12, None), seed: int = 0) -> list[dict]:
    """Train versus validation average precision as a decision tree gets deeper. Validation requesters are unseen.
    The tree is allowed to use the requester id on purpose: that is what overfitting looks like."""
    tr, va = splits.group_split(df, seed=seed)
    feats = AVAILABLE_AT_OPEN + [GROUP]
    rows = []
    for d in depths:
        m = build("tree", feats, max_depth=d).fit(tr[feats], tr[TARGET])
        rows.append({"max_depth": d,
                     "train": float(average_precision_score(tr[TARGET], m.predict_proba(tr[feats])[:, 1])),
                     "validation": float(average_precision_score(va[TARGET], m.predict_proba(va[feats])[:, 1]))})
    return rows


CANDIDATES = (("logistic", {"C": 0.01}), ("logistic", {"C": 0.1}), ("logistic", {"C": 1.0}),
              ("forest", {"min_samples_leaf": 5}), ("forest", {"min_samples_leaf": 20}))


def select_model(train: pd.DataFrame, features=AVAILABLE_AT_OPEN, folds: int = 5, candidates=CANDIDATES) -> list[dict]:
    """Grouped cross-validation on the training rows only: no fold shares a requester with its validation fold."""
    cv = GroupKFold(n_splits=folds)
    out = []
    for kind, params in candidates:
        oof = cross_val_predict(build(kind, features, **params), train[features], train[TARGET],
                                cv=cv, groups=train[GROUP], method="predict_proba")[:, 1]
        out.append({"kind": kind, "params": params, "cv_avg_precision": float(average_precision_score(train[TARGET], oof)), "oof": oof})
    return sorted(out, key=lambda r: -r["cv_avg_precision"])


def train_and_test(df: pd.DataFrame, cost_fn: float = 10.0, cost_fp: float = 1.0, seed: int = 0, features=AVAILABLE_AT_OPEN) -> dict:
    """Split once by requester. Choose the model and the threshold from the TRAINING rows (grouped CV, out-of-fold
    predictions). Touch the test rows exactly once, at the end."""
    tr, te = splits.group_split(df, seed=seed)
    assert splits.overlap(tr, te) == 0
    ranked = select_model(tr, features)
    best = ranked[0]
    thr = choose_threshold(tr[TARGET], best["oof"], cost_fn, cost_fp)
    final = build(best["kind"], features, **best["params"]).fit(tr[features], tr[TARGET])
    p = final.predict_proba(te[features])[:, 1]
    refs = reference_costs(te[TARGET], cost_fn, cost_fp)
    s = scores(te[TARGET], p, thr)
    return {
        "model": final, "chosen": {"kind": best["kind"], "params": best["params"]},
        "ranking": [{k: v for k, v in r.items() if k != "oof"} for r in ranked],
        "threshold": thr, "cost_fn": cost_fn, "cost_fp": cost_fp,
        "test": s, "confusion": confusion(te[TARGET], p, thr),
        "cost_model": float(cost(te[TARGET], p, thr, cost_fn, cost_fp)), "cost_reference": refs,
        "rows": {"train": len(tr), "test": len(te), "train_requesters": int(tr[GROUP].nunique()), "test_requesters": int(te[GROUP].nunique())},
        "features": list(features),
    }


def verdict(result: dict, min_lift: float = 2.0) -> tuple[bool, list[str]]:
    """Ship gate: better than the two do-nothing policies on cost, and average precision at least `min_lift` times the prevalence."""
    why = []
    best_ref = min(result["cost_reference"].values())
    if result["cost_model"] >= best_ref:
        why.append(f"cost {result['cost_model']:.0f} is not below the best do-nothing policy ({best_ref:.0f})")
    lift = result["test"]["avg_precision"] / result["test"]["prevalence"]
    if lift < min_lift:
        why.append(f"average precision is only {lift:.2f}x the prevalence (needs {min_lift:g}x)")
    return (not why), why


__all__ = ["compare_protocols", "baseline", "depth_curve", "select_model", "train_and_test", "verdict"]
