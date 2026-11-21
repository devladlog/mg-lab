"""Identifiers only Contoso knows. The service cannot know that CON-48213 is a badge number, so a local pattern pass runs
after the service redaction and before anything else sees the text."""
from __future__ import annotations

import re

PATTERNS = {"EmployeeId": re.compile(r"\bCON-\d{5}\b", re.IGNORECASE)}


def redact(text: str) -> tuple[str, list[str]]:
    """Returns (text with each hit replaced by [Name], the list of pattern names that hit, one entry per hit)."""
    hits: list[str] = []
    for name, rx in PATTERNS.items():
        text, n = rx.subn(f"[{name}]", text)
        hits += [name] * n
    return text, hits
