"""Metrics that survive class imbalance, and a threshold chosen from costs instead of from habit."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, roc_auc_score


def scores(y, p, threshold: float = 0.5) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    pred = p >= threshold
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "roc_auc": float(roc_auc_score(y, p)),
        "avg_precision": float(average_precision_score(y, p)),   # area under precision-recall: its floor is the prevalence
        "brier": float(brier_score_loss(y, p)),
        "prevalence": float(y.mean()),
    }


def confusion(y, p, threshold: float) -> dict:
    y, pred = np.asarray(y).astype(bool), np.asarray(p) >= threshold
    tp, fp = int((y & pred).sum()), int((~y & pred).sum())
    fn, tn = int((y & ~pred).sum()), int((~y & ~pred).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0}


def cost(y, p, threshold: float, cost_fn: float, cost_fp: float) -> float:
    c = confusion(y, p, threshold)
    return c["fn"] * cost_fn + c["fp"] * cost_fp


def choose_threshold(y, p, cost_fn: float, cost_fp: float) -> float:
    """The threshold with the lowest total cost on these predictions (use out-of-fold predictions, never the test set)."""
    grid = np.unique(np.round(np.asarray(p), 4))
    best = min(grid, key=lambda t: (cost(y, p, t, cost_fn, cost_fp), -t))
    return float(best)


def reference_costs(y, cost_fn: float, cost_fp: float) -> dict:
    y = np.asarray(y)
    return {"flag_nothing": float(y.sum() * cost_fn), "flag_everything": float((len(y) - y.sum()) * cost_fp)}
