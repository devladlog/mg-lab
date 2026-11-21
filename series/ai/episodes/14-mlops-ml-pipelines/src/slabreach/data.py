"""Fictional ticket history, generated from a stated rule plus noise. It is NOT real service-desk data: it exists so the
pipeline has something to learn and so the gate can be shown failing on purpose."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import CATEGORIES, CHANNELS, LABEL, PRIORITIES, RAW_COLUMNS

SCENARIOS = ("baseline", "noisy", "missing-column")
BASE = {"P1": 0.3, "P2": -0.5, "P3": -1.2, "P4": -2.0}
CAT = {"network": 0.9, "access": -0.7, "hardware": 0.5, "software": 0.0, "email": -0.2}
CHAN = {"phone": -0.7, "portal": 0.0, "email": 0.7}


def generate(n: int = 6000, seed: int = 1, scenario: str = "baseline", start: str = "2026-01-05") -> pd.DataFrame:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    rng = np.random.default_rng(seed)
    days = rng.integers(0, 90, n)
    minutes = rng.integers(7 * 60, 20 * 60, n)
    created = pd.to_datetime(start) + pd.to_timedelta(days, "D") + pd.to_timedelta(minutes, "m")
    prio = rng.choice(PRIORITIES, n, p=[.08, .22, .45, .25])
    cat = rng.choice(CATEGORIES, n)
    chan = rng.choice(CHANNELS, n, p=[.3, .45, .25])
    tl = np.clip(rng.lognormal(5.0, 0.7, n), 20, 4000).astype(int)
    hour, wd = created.hour, created.weekday
    z = (np.vectorize(BASE.get)(prio) + np.vectorize(CAT.get)(cat) + np.vectorize(CHAN.get)(chan)
         + 0.9 * ((hour < 9) | (hour >= 17)) + 0.6 * ((wd == 4) & (hour >= 15)) + 0.001 * (tl - 150))
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    if scenario == "noisy":                         # a bad extract: a third of the labels are coin flips
        flip = rng.random(n) < 0.35
        y = np.where(flip, rng.integers(0, 2, n), y)
    df = pd.DataFrame({"ticket_id": [f"T{seed:02d}{i:05d}" for i in range(n)], "created_at": created.strftime("%Y-%m-%dT%H:%M:%S"),
                       "priority": prio, "category": cat, "channel": chan, "text_length": tl, LABEL: y})
    df = df.sort_values("created_at").reset_index(drop=True)[RAW_COLUMNS]
    if scenario == "missing-column":                # an upstream rename: the pipeline must refuse, not guess
        df = df.drop(columns=["channel"])
    return df
