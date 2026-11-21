"""Blind review: shuffle the answers of every task, label them A, B, C..., collect human scores 1-5, then unblind.
The rules in scoring.py measure what can be checked; this measures what a person prefers without knowing which AI wrote it."""
from __future__ import annotations

import random
import string


def make_sheet(results: dict, seed: int = 20261121) -> tuple[str, dict]:
    rng = random.Random(seed)
    key: dict[str, dict[str, str]] = {}
    out = ["# Blind review sheet", "",
           "Score each answer 1 (unusable) to 5 (I would send it as is). Do not guess which AI wrote it. Put the scores in scores.json as",
           '`{"<task>": {"A": 4, "B": 2}}`.', ""]
    tasks = []
    for r in results["rows"]:
        if r["task"] not in tasks:
            tasks.append(r["task"])
    for t in tasks:
        rows = [r for r in results["rows"] if r["task"] == t and r["repeat"] == 0 and not r["error"] and r["answer"].strip()]
        rng.shuffle(rows)
        labels = string.ascii_uppercase
        key[t] = {labels[i]: r["provider"] for i, r in enumerate(rows)}
        out += [f"## {t}", ""]
        for i, r in enumerate(rows):
            out += [f"### Answer {labels[i]}", "", "```text", r["answer"].strip(), "```", ""]
    return "\n".join(out), key


def unblind(results: dict, key: dict, scores: dict) -> dict:
    """Attach human_score to repeat-0 rows. Unknown tasks, labels or out-of-range scores raise, never pass silently."""
    for t, by_label in scores.items():
        if t not in key:
            raise ValueError(f"scores mention unknown task {t!r}")
        for label, val in by_label.items():
            if label not in key[t]:
                raise ValueError(f"task {t}: no answer labelled {label!r}")
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not 1 <= val <= 5:
                raise ValueError(f"task {t} answer {label}: score must be 1 to 5, got {val!r}")
            for r in results["rows"]:
                if r["task"] == t and r["provider"] == key[t][label] and r["repeat"] == 0:
                    r["human_score"] = float(val)
    return results
