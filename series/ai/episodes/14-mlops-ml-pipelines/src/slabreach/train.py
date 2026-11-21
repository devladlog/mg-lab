"""Component 2: fit the model and save it as an MLflow model (the format Azure ML can deploy without a scoring script)."""
from __future__ import annotations

from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .schema import CAT_FEATURES, FEATURES, LABEL, NUM_FEATURES, RAW_FILE


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["created_at"])
    out = df[["priority", "category", "channel", "text_length"]].copy()
    out["hour"], out["weekday"] = ts.dt.hour, ts.dt.weekday
    out["text_length"] = out["text_length"].astype(float)
    out["hour"], out["weekday"] = out["hour"].astype(float), out["weekday"].astype(float)
    return out[FEATURES]


def build(seed: int, max_iter: int) -> Pipeline:
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES)], remainder="passthrough")
    return Pipeline([("pre", pre), ("clf", HistGradientBoostingClassifier(max_iter=max_iter, learning_rate=0.05, max_depth=3, min_samples_leaf=40, random_state=seed))])


def run(train_dir: Path, model_out: Path, seed: int = 7, max_iter: int = 120) -> float:
    df = pd.read_csv(train_dir / RAW_FILE)
    X, y = featurize(df), df[LABEL]
    pipe = build(seed, max_iter).fit(X, y)
    auc = float(roc_auc_score(y, pipe.predict_proba(X)[:, 1]))
    mlflow.log_params({"seed": seed, "max_iter": max_iter, "rows": len(df), "features": ",".join(FEATURES)})
    mlflow.log_metric("train_auc", auc)
    # the endpoint returns the breach probability for each ticket; the signature is what AML turns into its Swagger contract
    sig = infer_signature(X, pipe.predict_proba(X.head(5)))
    mlflow.sklearn.save_model(pipe, str(model_out), signature=sig, pyfunc_predict_fn="predict_proba",
                              serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE)
    print(f"trained on {len(df)} rows, train AUC {auc:.3f}, model saved to {model_out}")
    return auc
