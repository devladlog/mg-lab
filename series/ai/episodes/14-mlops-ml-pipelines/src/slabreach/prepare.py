"""Component 1: validate the raw extract, split by TIME (the model is judged on tickets newer than it trained on), write both
halves. Exit code 2 on any validation error, with every problem listed."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .schema import CATEGORIES, CHANNELS, LABEL, PRIORITIES, RAW_COLUMNS, RAW_FILE

MIN_ROWS = 500
POSITIVE_RATE = (0.03, 0.60)          # a label rate outside this band is a data problem before it is a model problem


def validate(df: pd.DataFrame) -> list[str]:
    errs: list[str] = []
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        return [f"missing columns: {', '.join(missing)}"]
    if len(df) < MIN_ROWS:
        errs.append(f"{len(df)} rows, need at least {MIN_ROWS}")
    nulls = df[RAW_COLUMNS].isna().sum()
    errs += [f"{c}: {int(n)} empty values" for c, n in nulls.items() if n]
    for col, allowed in (("priority", PRIORITIES), ("category", CATEGORIES), ("channel", CHANNELS)):
        bad = sorted(set(df[col].dropna()) - set(allowed))
        if bad:
            errs.append(f"{col}: unexpected values {bad[:5]}")
    if not set(df[LABEL].dropna().unique()) <= {0, 1}:
        errs.append(f"{LABEL} must be 0 or 1")
    elif len(df):
        rate = float(df[LABEL].mean())
        if not POSITIVE_RATE[0] <= rate <= POSITIVE_RATE[1]:
            errs.append(f"breach rate {rate:.1%} is outside {POSITIVE_RATE[0]:.0%}-{POSITIVE_RATE[1]:.0%}")
    if (pd.to_numeric(df["text_length"], errors="coerce") <= 0).any():
        errs.append("text_length must be a positive number")
    if pd.to_datetime(df["created_at"], errors="coerce").isna().any():
        errs.append("created_at has values that are not dates")
    return errs


def run(raw: Path, train_out: Path, test_out: Path, test_fraction: float = 0.2) -> int:
    src = raw / RAW_FILE
    if not src.exists():
        print(f"ERROR: {src} not found")
        return 2
    df = pd.read_csv(src)
    errs = validate(df)
    if errs:
        print("DATA VALIDATION FAILED")
        for e in errs:
            print(" -", e)
        return 2
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.sort_values("created_at").reset_index(drop=True)
    cut = int(len(df) * (1 - test_fraction))
    train, test = df.iloc[:cut], df.iloc[cut:]
    for d, part in ((train_out, train), (test_out, test)):
        d.mkdir(parents=True, exist_ok=True)
        part.to_csv(d / RAW_FILE, index=False)
    report = {"rows": len(df), "train_rows": len(train), "test_rows": len(test), "breach_rate": round(float(df[LABEL].mean()), 4),
              "train_ends": str(train.created_at.max()), "test_starts": str(test.created_at.min())}
    (train_out / "data_report.json").write_text(json.dumps(report, indent=2))
    print("data ok:", json.dumps(report))
    return 0
