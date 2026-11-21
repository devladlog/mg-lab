"""Preprocessing and model live in ONE pipeline, so every statistic (imputation, scaling, one-hot categories) is learned
from the training rows only. Fitting the scaler on all data first is a leak that no split can undo."""
from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from .data import CATEGORICAL, GROUP, NUMERIC


def preprocessor(categorical: list[str], numeric: list[str], scale: bool = True) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median"))] + ([("scale", StandardScaler())] if scale else [])
    parts = []
    if numeric:
        parts.append(("num", Pipeline(num_steps), numeric))
    if categorical:
        parts.append(("cat", OneHotEncoder(handle_unknown="ignore"), categorical))
    return ColumnTransformer(parts)


def columns_for(features: list[str]) -> tuple[list[str], list[str]]:
    cat = [c for c in features if c in CATEGORICAL or c == GROUP]
    num = [c for c in features if c in NUMERIC or c not in cat]
    return cat, num


def build(kind: str, features: list[str], **params) -> Pipeline:
    cat, num = columns_for(features)
    if kind == "dummy":
        est = DummyClassifier(strategy="prior")
        return Pipeline([("pre", preprocessor(cat, num)), ("model", est)])
    if kind == "logistic":
        est = LogisticRegression(C=params.get("C", 1.0), max_iter=2000)
        return Pipeline([("pre", preprocessor(cat, num)), ("model", est)])
    if kind == "forest":
        est = RandomForestClassifier(n_estimators=params.get("n_estimators", 100), min_samples_leaf=params.get("min_samples_leaf", 5),
                                     random_state=0, n_jobs=1)
        return Pipeline([("pre", preprocessor(cat, num, scale=False)), ("model", est)])
    if kind == "tree":
        est = DecisionTreeClassifier(max_depth=params.get("max_depth"), random_state=0)
        return Pipeline([("pre", preprocessor(cat, num, scale=False)), ("model", est)])
    raise ValueError(f"unknown model kind {kind!r}")
