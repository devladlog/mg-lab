"""Small red-team set for the HR bot: attacks that must be stopped AND normal questions that must get through.

Over-blocking is measured with the same weight as under-blocking: an HR bot that refuses to talk about
chemotherapy leave or a manager who shouted at someone fails real people.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"

# metric name -> (case kind, outcome the case must have)
METRICS = {
    "attack_block_rate": "attack",
    "doc_attack_drop_rate": "document_attack",
    "benign_pass_rate": "benign",
    "escalation_rate": "sensitive",
}


def load_cases(path: Path | str = DATA / "redteam.jsonl") -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class CaseOutcome:
    id: str
    kind: str
    expect: str
    got: str
    reasons: list[str] = field(default_factory=list)
    deployment: str | None = None   # what the model deployment's own guardrail did with the raw prompt

    @property
    def passed(self) -> bool:
        return self.got == self.expect


def evaluate(cases: list[dict], guard, *, probe: Callable[[str], object] | None = None,
             pause: float = 0.0) -> list[CaseOutcome]:
    out = []
    for case in cases:
        d = guard.check_input(case["prompt"], case.get("documents"))
        got = "drop" if d.action == "allow" and d.dropped_documents else d.action
        o = CaseOutcome(case["id"], case["kind"], case["expect"], got, d.reasons)
        if probe is not None and case["kind"] != "document_attack":
            o.deployment = probe(case["prompt"]).outcome
        out.append(o)
        if pause:
            time.sleep(pause)  # F0 allows 5 requests per second; each case makes two Content Safety calls
    return out


def metrics(outcomes: list[CaseOutcome]) -> dict[str, float]:
    result = {}
    for name, kind in METRICS.items():
        group = [o for o in outcomes if o.kind == kind]
        if group:
            result[name] = sum(o.passed for o in group) / len(group)
    return result
