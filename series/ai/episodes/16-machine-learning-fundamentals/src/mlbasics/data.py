"""Synthetic, fictional tickets for the Contoso Porto service desk. NOT real data: it is generated with a fixed seed from
a known recipe so every pitfall in this episode is planted on purpose and can be detected by a test:

  * rare positives          ~13 % of tickets breach their SLA        -> accuracy is a trap
  * a leaking column        first_response_minutes exists only after the ticket was picked up -> not available at prediction time
  * repeat requesters       each employee has a personal propensity (requester effect) -> random splits leak identity
  * time                    opened_day 0..179 -> a deployed model is used on later days than it was trained on
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

TARGET = "breached_sla"
GROUP = "requester_id"
TIME = "opened_day"
CATEGORICAL = ["priority", "category", "department", "language"]
NUMERIC = ["hour_opened", "weekday", "queue_backlog", "attachments", "text_length", "is_vip"]
# what the dispatcher knows when the ticket arrives. requester_id is an identifier, not a feature (see audit / compare).
AVAILABLE_AT_OPEN = CATEGORICAL + NUMERIC
LEAKY = ["first_response_minutes"]          # only known after the ticket is picked up

CATEGORIES = ["hardware", "software", "access", "network", "email", "other"]
DEPARTMENTS = ["finance", "hr", "sales", "engineering", "operations", "legal"]


def generate(n: int = 8000, requesters: int = 500, days: int = 180, seed: int = 20261121) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    req = rng.integers(0, requesters, n)
    req_effect = rng.normal(0, 1, requesters)                 # personal propensity, constant per employee
    req_dept = rng.integers(0, len(DEPARTMENTS), requesters)  # an employee belongs to one department
    req_lang = rng.random(requesters) < 0.6                   # True = pt
    day = np.sort(rng.integers(0, days, n))
    priority = rng.choice(["P1", "P2", "P3", "P4"], n, p=[0.05, 0.15, 0.40, 0.40])
    category = rng.choice(CATEGORIES, n, p=[0.20, 0.25, 0.20, 0.15, 0.12, 0.08])
    hour = np.clip(rng.normal(11, 4.5, n), 0, 23).astype(int)
    weekday = rng.choice(7, n, p=[0.19, 0.19, 0.19, 0.19, 0.17, 0.04, 0.03])
    backlog = rng.poisson(8 + 0.5 * np.abs(hour - 12), n)
    attachments = rng.choice([0, 1, 2, 3], n, p=[0.55, 0.30, 0.10, 0.05])
    text_length = np.clip(rng.lognormal(5.0, 0.7, n), 20, 4000).round().astype(float)
    is_vip = (rng.random(n) < 0.05).astype(int)

    logit = (-4.6
             + np.select([priority == "P1", priority == "P2"], [1.6, 0.8], 0.0)
             + np.select([category == "network", category == "access"], [1.2, -0.6], 0.0)
             + 0.12 * backlog
             + 1.2 * ((hour < 8) | (hour >= 18))
             + 0.9 * (weekday >= 5)
             - 0.8 * is_vip
             + 0.0012 * text_length
             + 1.0 * req_effect[req])
    breach = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    first_resp = np.clip(np.where(breach == 1, rng.normal(190, 70, n), rng.normal(40, 25, n)), 1, None).round()
    text_length[rng.random(n) < 0.03] = np.nan                # a few missing values, as in real exports
    return pd.DataFrame({
        GROUP: [f"E{r:04d}" for r in req],
        TIME: day,
        "priority": priority, "category": category,
        "department": np.array(DEPARTMENTS)[req_dept[req]],
        "language": np.where(req_lang[req], "pt", "en"),
        "hour_opened": hour, "weekday": weekday, "queue_backlog": backlog, "attachments": attachments,
        "text_length": text_length, "is_vip": is_vip,
        "first_response_minutes": first_resp,
        TARGET: breach,
    })


def fingerprint(df: pd.DataFrame) -> str:
    """Short hash of the table, recorded in the model card so a result can be tied to the exact data."""
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16]
