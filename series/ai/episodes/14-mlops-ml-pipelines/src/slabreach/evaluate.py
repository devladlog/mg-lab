"""Component 3: judge the saved model on the newer tickets and write decision.json. Exit code 3 if the gate says no, so the
pipeline job FAILS and nothing downstream (registration, deployment) can run."""
from __future__ import annotations

import json
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from . import gate
from .schema import LABEL, RAW_FILE
from .train import featurize


def metrics_for(model_dir: Path, test_dir: Path) -> dict:
    df = pd.read_csv(test_dir / RAW_FILE)
    X, y = featurize(df), df[LABEL].to_numpy()
    p = np.asarray(mlflow.pyfunc.load_model(str(model_dir)).predict(X))[:, 1]       # the model as it will be SERVED (pyfunc)
    p1 = (df["priority"] == "P1").to_numpy() & (y == 1)
    recall = float(((p >= gate.THRESHOLD) & p1).sum() / p1.sum()) if p1.sum() else None
    return {"auc": float(roc_auc_score(y, p)), "avg_precision": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)), "p1_recall": recall, "test_rows": int(len(y)), "p1_breaches": int(p1.sum())}


def run(model_dir: Path, test_dir: Path, out_dir: Path, baseline_auc: float = 0.0) -> int:
    m = metrics_for(model_dir, test_dir)
    d = gate.decide(m, baseline_auc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decision.json").write_text(json.dumps({"promote": d.promote, "reasons": d.reasons, "baseline_auc": baseline_auc,
                                                       "metrics": m, "thresholds": {"min_auc": gate.MIN_AUC, "max_auc_drop": gate.MAX_AUC_DROP,
                                                       "min_p1_recall": gate.MIN_P1_RECALL, "threshold": gate.THRESHOLD}}, indent=2))
    for k in ("auc", "avg_precision", "brier", "p1_recall"):
        if m[k] is not None:
            mlflow.log_metric(f"test_{k}", m[k])
    mlflow.log_metric("promote", float(d.promote))
    print(f"test AUC {m['auc']:.3f} (production {baseline_auc:.3f}), P1 recall {m['p1_recall']}, rows {m['test_rows']}")
    print("PROMOTE" if d.promote else "REJECT", "-", "; ".join(d.reasons))
    return 0 if d.promote else 3
