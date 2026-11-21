"""The promotion rules, as a pure function. Every number is OURS: tune it on your own history, not on this fictional data."""
from __future__ import annotations

from dataclasses import dataclass, field

MIN_AUC = 0.70                # absolute floor: below this the model is not worth serving
MAX_AUC_DROP = 0.02           # relative: seeds 1 to 3 of the fictional data differ by up to ~0.03 on a 1,200-row test set, so 0.005 would reject noise
MIN_P1_RECALL = 0.60          # slice: urgent tickets are why the model exists; a good average can hide a bad slice
THRESHOLD = 0.50              # probability above which we say "will breach"; used for the slice recall


@dataclass
class Decision:
    promote: bool
    metrics: dict
    reasons: list[str] = field(default_factory=list)
    baseline_auc: float = 0.0


def decide(metrics: dict, baseline_auc: float = 0.0) -> Decision:
    reasons: list[str] = []
    if metrics["auc"] < MIN_AUC:
        reasons.append(f"AUC {metrics['auc']:.3f} is below the floor {MIN_AUC}")
    if baseline_auc and metrics["auc"] < baseline_auc - MAX_AUC_DROP:
        reasons.append(f"AUC {metrics['auc']:.3f} is worse than production {baseline_auc:.3f} by more than {MAX_AUC_DROP}")
    if metrics["p1_recall"] is None:
        reasons.append("no P1 breaches in the test set: the slice check cannot run")
    elif metrics["p1_recall"] < MIN_P1_RECALL:
        reasons.append(f"P1 breach recall {metrics['p1_recall']:.2f} at threshold {THRESHOLD} is below {MIN_P1_RECALL}")
    return Decision(not reasons, metrics, reasons or ["all checks passed"], baseline_auc)
