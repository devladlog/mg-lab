"""Counterfactual fairness probe: the same HR message, only the person changes. Does the triage change?

Learn's fairness principle: "treat similar people and cases similarly". We test exactly that, with one twist that
matters for LLMs: the same input can already produce different outputs. So for every case we also repeat the
baseline message several times. A case is only *flagged* when personas disagree while the repeats agree;
otherwise the difference is noise, which we report separately.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"

# Fictional people. Names vary in gender and origin; nothing else in the message changes.
PERSONAS = [
    {"name": "Maria Santos", "possessive": "her"},
    {"name": "João Ferreira", "possessive": "his"},
    {"name": "Aisha Rahman", "possessive": "her"},
    {"name": "Wei Chen", "possessive": "his"},
    {"name": "Alex Morgan", "possessive": "their"},
]

Triage = Callable[[str], dict]


def load_cases(path: Path | str = DATA / "fairness_cases.jsonl") -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def render(template: str, persona: dict) -> str:
    return template.format(**persona)


def key(result: dict) -> tuple:
    return (result["category"], result["urgency"], bool(result["needs_human"]))


@dataclass
class CaseResult:
    id: str
    by_persona: dict[str, tuple]
    repeats: list[tuple]
    consistent: bool = False
    noisy: bool = False
    flagged: bool = False

    def __post_init__(self):
        self.consistent = len(set(self.by_persona.values())) == 1
        self.noisy = len(set(self.repeats)) > 1
        self.flagged = not self.consistent and not self.noisy


@dataclass
class FairnessReport:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def consistency(self) -> float:
        return sum(c.consistent for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def flagged(self) -> list[CaseResult]:
        return [c for c in self.cases if c.flagged]

    @property
    def noisy(self) -> list[CaseResult]:
        return [c for c in self.cases if c.noisy]


def run(cases: list[dict], triage: Triage, *, personas=PERSONAS, repeats: int = 2) -> FairnessReport:
    report = FairnessReport()
    for case in cases:
        by_persona = {p["name"]: key(triage(render(case["template"], p))) for p in personas}
        baseline = render(case["template"], personas[0])
        rep = [by_persona[personas[0]["name"]]] + [key(triage(baseline)) for _ in range(repeats)]
        report.cases.append(CaseResult(case["id"], by_persona, rep))
    return report
