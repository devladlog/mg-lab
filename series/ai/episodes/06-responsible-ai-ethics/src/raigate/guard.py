"""App-level guard for the HR bot: what happens to a question *before* the model sees it, and to the answer after.

Rules (ours, not the service's - Content Safety only measures, it doesn't decide):
- Prompt attack on the user prompt -> block.
- Document attack in a retrieved chunk -> drop that chunk, keep the question (one poisoned page shouldn't silence
  the bot) and log it.
- Self-harm signal in the question -> escalate: no model answer, route to a person with support contacts.
  Blocking someone who says they are struggling is a harm too.
- Hate / sexual / violence at medium or above (severity >= 4) -> block. Low (2) passes: "this deadline is killing
  me" or reporting that a manager shouted at you must get an answer.
- The answer: anything at low or above (>= 2) is withheld. We hold what *we* say to a stricter bar.

    PYTHONPATH=src python -m raigate.guard "question" [--doc "retrieved text" ...] --safety-endpoint $CS
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field

from .safety import ShieldResult, analyze, make_safety_client, shield

INPUT_BLOCK_AT = {"Hate": 4, "Sexual": 4, "Violence": 4}
ESCALATE_AT = {"SelfHarm": 2}
OUTPUT_WITHHOLD_AT = {"Hate": 2, "Sexual": 2, "Violence": 2, "SelfHarm": 2}

ESCALATION_MESSAGE = ("Thank you for telling us. You don't have to handle this alone: a person from the Contoso "
                      "wellbeing team will contact you today. If you are in immediate danger, call 112.")


@dataclass
class Decision:
    action: str                      # allow | block | escalate
    reasons: list[str] = field(default_factory=list)
    dropped_documents: list[int] = field(default_factory=list)
    kept_documents: list[str] = field(default_factory=list)
    severities: dict[str, int] = field(default_factory=dict)


def decide_input(shields: ShieldResult, severities: dict[str, int], documents: list[str]) -> Decision:
    """Pure decision logic over the two Content Safety results (unit-tested without any service)."""
    d = Decision(action="allow", severities=dict(severities))
    for i, attacked in enumerate(shields.document_attacks):
        if attacked:
            d.dropped_documents.append(i)
            d.reasons.append(f"document {i} dropped: document attack (injected instructions)")
    d.kept_documents = [doc for i, doc in enumerate(documents) if i not in d.dropped_documents]
    if shields.user_attack:
        d.action = "block"
        d.reasons.append("user prompt attack detected")
        return d
    for cat, level in INPUT_BLOCK_AT.items():        # Hate, Sexual, Violence: 4 (medium)
        if severities.get(cat, 0) >= level:
            d.action = "block"
            d.reasons.append(f"{cat} severity {severities[cat]} >= {level}")
    if d.action == "allow":
        for cat, level in ESCALATE_AT.items():       # SelfHarm: 2 (low)
            if severities.get(cat, 0) >= level:
                d.action = "escalate"
                d.reasons.append(f"{cat} severity {severities[cat]} >= {level}: route to a person")
    return d


def decide_output(severities: dict[str, int]) -> Decision:
    hits = [f"{c} severity {severities.get(c, 0)} >= {lvl}" for c, lvl in OUTPUT_WITHHOLD_AT.items()
            if severities.get(c, 0) >= lvl]
    return Decision(action="block" if hits else "allow", reasons=hits, severities=dict(severities))


class Guard:
    def __init__(self, safety_client):
        self.client = safety_client

    def check_input(self, question: str, documents: list[str] | None = None) -> Decision:
        documents = list(documents or [])
        return decide_input(shield(self.client, question, documents), analyze(self.client, question), documents)

    def check_output(self, answer: str) -> Decision:
        return decide_output(analyze(self.client, answer))


def main(argv=None, *, safety_client=None) -> int:
    ap = argparse.ArgumentParser(description="Run one question (and optional retrieved documents) through the guard")
    ap.add_argument("question")
    ap.add_argument("--doc", action="append", default=[], help="retrieved document text (repeatable, max 5)")
    ap.add_argument("--safety-endpoint", help="https://<name>.cognitiveservices.azure.com/")
    a = ap.parse_args(argv)
    if safety_client is None:
        if not a.safety_endpoint:
            ap.error("--safety-endpoint is required")
        safety_client = make_safety_client(a.safety_endpoint)
    d = Guard(safety_client).check_input(a.question, a.doc)
    out = asdict(d)
    out.pop("kept_documents")
    print(json.dumps(out, indent=2))
    if d.action == "escalate":
        print("\n" + ESCALATION_MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
