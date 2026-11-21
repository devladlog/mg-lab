"""Checks around the model, not inside it. They can only RAISE needs_human, never lower it.

They are cheap heuristics, not a defence: the real controls are that the model has no tools, its answer is a
schema-checked ticket, and a person reads anything flagged."""
from __future__ import annotations

import re

from .ticket import Ticket

CODE = re.compile(r"\b([A-Z]{2,3})[\s\-]?(\d{3,5})\b")
INJECTION = [
    re.compile(r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above)\s+(instructions|rules)", re.I),
    re.compile(r"(set|mark|change)\s+(the\s+)?(severity|queue|priority)", re.I),
    re.compile(r"(system|developer)\s+prompt", re.I),
    re.compile(r"you\s+are\s+now\b", re.I),
    re.compile(r"\bdo\s+not\s+(escalate|tell|flag)", re.I),
]


def norm(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


def codes_in(text: str) -> set[str]:
    return {norm(a + b) for a, b in CODE.findall(text.upper())}


def injection_hits(text: str) -> list[str]:
    return [p.pattern for p in INJECTION if p.search(text or "")]


def apply(ticket: Ticket, transcript: str | None) -> Ticket:
    """Return the ticket with flags; needs_human only goes from False to True."""
    flags = list(ticket.flags)
    if transcript:
        spoken = codes_in(transcript)
        shown = norm(ticket.error_code)
        if spoken and shown and shown not in spoken:
            flags.append(f"conflict: screenshot shows {ticket.error_code}, voice note says {sorted(spoken)}")
        elif spoken and not shown:
            flags.append("conflict: the voice note names an error code but none was read from the screenshot")
    if injection_hits(ticket.ocr_text) or injection_hits(transcript or ""):
        flags.append("possible prompt injection in the screenshot text or the voice note")
    if not ticket.error_code:
        flags.append("no error code could be read")
    risky = any(f.startswith(("conflict", "possible prompt", "no error code")) for f in flags)   # a ticket without a code needs a person
    return Ticket(ticket.product, ticket.error_code, ticket.severity, ticket.queue,
                  ticket.needs_human or risky, ticket.summary, ticket.ocr_text, flags)
