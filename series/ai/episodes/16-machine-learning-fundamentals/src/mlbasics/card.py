"""A model card is a small JSON file next to the model: what data, what split, what numbers, what threshold, what it must not be used for."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from .data import GROUP, LEAKY, fingerprint


class ScoreError(ValueError):
    pass


def make_card(df: pd.DataFrame, result: dict) -> dict:
    return {
        "name": "contoso-porto-sla-breach-risk",
        "data": {"source": "synthetic, fixed seed (mlbasics.data.generate)", "rows": len(df), "fingerprint": fingerprint(df)},
        "split": {"policy": "group split by requester (no employee on both sides), then grouped 5-fold CV inside the training rows",
                  **result["rows"]},
        "features": result["features"],
        "excluded": {"identifier": GROUP, "not available when the ticket arrives": LEAKY},
        "model": result["chosen"],
        "threshold": {"value": result["threshold"], "cost_false_negative": result["cost_fn"], "cost_false_positive": result["cost_fp"],
                      "chosen_on": "out-of-fold predictions of the training rows"},
        "test": {k: round(v, 4) for k, v in result["test"].items()},
        "confusion_at_threshold": result["confusion"],
        "cost_on_test": {"model": result["cost_model"], **result["cost_reference"]},
        "intended_use": "rank new tickets by SLA-breach risk so a dispatcher looks at the riskiest first",
        "not_for": ["decisions about people", "tickets from other organisations", "any use before it is re-validated on real, anonymised data"],
    }


def save(result: dict, card: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mp, cp = out / "model.joblib", out / "model_card.json"
    joblib.dump(result["model"], mp)
    cp.write_text(json.dumps(card, indent=2), encoding="utf-8")
    return mp, cp


def score_ticket(model_path: str | Path, card_path: str | Path, ticket: dict) -> dict:
    """Risk for ONE new ticket. Refuses columns that are not known at arrival and requires every feature the model was trained on."""
    card = json.loads(Path(card_path).read_text(encoding="utf-8"))
    leaked = [c for c in LEAKY if c in ticket]
    if leaked:
        raise ScoreError(f"{leaked} are not known when the ticket arrives and were not used to train the model; remove them")
    missing = [c for c in card["features"] if c not in ticket]
    if missing:
        raise ScoreError(f"missing fields: {missing}")
    model = joblib.load(model_path)
    p = float(model.predict_proba(pd.DataFrame([{c: ticket[c] for c in card["features"]}]))[0, 1])
    thr = card["threshold"]["value"]
    return {"risk": p, "threshold": thr, "flag_for_dispatcher": p >= thr}


__all__ = ["make_card", "save", "score_ticket", "ScoreError"]
