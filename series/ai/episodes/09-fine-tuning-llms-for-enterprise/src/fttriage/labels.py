"""The triage contract (same labels as episodes 6 and 8) and how a model answer is parsed."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

CATEGORIES = ["leave", "payroll", "benefits", "conduct", "equipment", "career", "other"]
URGENCIES = ["low", "normal", "high"]


@dataclass(frozen=True)
class Label:
    category: str
    urgency: str
    needs_human: bool

    def to_json(self) -> str:
        """The exact text the model is trained to produce: compact, fixed key order."""
        return json.dumps({"category": self.category, "urgency": self.urgency, "needs_human": self.needs_human},
                          separators=(",", ":"))


def parse_label(text: str | None) -> Label | None:
    """Strict parse of a model answer. Anything but one JSON object with valid values is None (a format error).
    A fenced ```json block is tolerated because base models like to add one; prose around the JSON is not."""
    if not text:
        return None
    s = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", s, flags=re.S)
    if m:
        s = m.group(1)
    try:
        d = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or set(d) != {"category", "urgency", "needs_human"}:
        return None
    if d["category"] not in CATEGORIES or d["urgency"] not in URGENCIES or not isinstance(d["needs_human"], bool):
        return None
    return Label(d["category"], d["urgency"], d["needs_human"])
