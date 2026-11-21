"""The two things the bot can DO: open a ticket (slot filling) and hand over to a person. Code decides what is valid."""
from __future__ import annotations

import json
import re
import unicodedata

from .session import Session

URGENCIES = ("low", "normal", "high")
MAX_TICKETS_PER_SESSION = 3
EMAIL_RE = re.compile(r"^[A-Za-z0-9._+-]+@contoso\.com$")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Open an IT ticket. Call it only when you have ALL four values from the employee in this "
                           "conversation. Never guess a value; ask for the missing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product": {"type": "string", "description": "The product or device affected, e.g. Contoso Connect VPN"},
                    "symptom": {"type": "string", "description": "What goes wrong, in the employee's words, one sentence"},
                    "urgency": {"type": "string", "enum": list(URGENCIES),
                                "description": "high = the employee cannot work at all; normal = work is slowed; low = no impact"},
                    "contact": {"type": "string", "description": "The employee's work e-mail address (name@contoso.com)"},
                },
                "required": ["product", "symptom", "urgency", "contact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_to_human",
            "description": "Pass the conversation to a person on the service desk. Use it when the employee asks for a "
                           "person, is upset, or the request is outside IT support.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string", "description": "One short sentence for the person who takes over"}},
                "required": ["reason"],
            },
        },
    },
]

# A tripwire, not understanding: the person asked for a human in plain words, so we do not wait for the model.
_HUMAN_PHRASES = (
    "talk to a person", "talk to a human", "speak to a person", "speak to a human", "speak to someone",
    "talk to someone", "real person", "human agent", "service desk agent",
    "falar com uma pessoa", "falar com alguem", "falar com um humano", "falar com um colega", "quero uma pessoa",
    "atendimento humano", "passar para uma pessoa",
)


def _fold_text(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def wants_human(text: str) -> bool:
    t = _fold_text(text)
    return any(p in t for p in _HUMAN_PHRASES)


def start_handoff(session: Session, reason: str) -> None:
    session.state = "handoff"
    session.handoff_reason = reason.strip()[:200] or "no reason given"


def create_ticket(session: Session, args: dict) -> dict:
    """Validate every slot. Returns {"ok": True, "ticket_id": ...} or {"ok": False, "missing": [...], "errors": [...]}."""
    missing = [k for k in ("product", "symptom", "urgency", "contact") if not str(args.get(k, "")).strip()]
    errors: list[str] = []
    if "urgency" not in missing and args["urgency"] not in URGENCIES:
        errors.append(f"urgency must be one of {list(URGENCIES)}")
    if "contact" not in missing and not EMAIL_RE.match(args["contact"].strip()):
        errors.append("contact must be a work address ending in @contoso.com")
    if "symptom" not in missing and len(args["symptom"].strip()) < 10:
        errors.append("symptom is too short to be useful")
    if "product" not in missing and len(args["product"].strip()) > 80:
        errors.append("product is too long")
    if missing or errors:
        return {"ok": False, "missing": missing, "errors": errors}
    key = (args["product"].strip().lower(), args["symptom"].strip().lower(), args["contact"].strip().lower())
    for t in session.tickets:                                   # idempotent: the same request returns the same ticket
        if (t["product"].lower(), t["symptom"].lower(), t["contact"].lower()) == key:
            return {"ok": True, "ticket_id": t["ticket_id"], "duplicate": True}
    if len(session.tickets) >= MAX_TICKETS_PER_SESSION:
        return {"ok": False, "missing": [], "errors": [f"at most {MAX_TICKETS_PER_SESSION} tickets per conversation; hand over to a person"]}
    ticket = {"ticket_id": f"INC-{1000 + len(session.tickets) + 1}", "product": args["product"].strip(),
              "symptom": args["symptom"].strip(), "urgency": args["urgency"], "contact": args["contact"].strip()}
    session.tickets.append(ticket)
    return {"ok": True, "ticket_id": ticket["ticket_id"]}


def run_tool(session: Session, name: str, raw_arguments: str) -> str:
    """Execute one tool call from the model. The arguments are model output: parse and validate, never trust."""
    try:
        args = json.loads(raw_arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError:
        return json.dumps({"ok": False, "errors": ["arguments were not a valid JSON object"]})
    if name == "create_ticket":
        return json.dumps(create_ticket(session, args))
    if name == "handoff_to_human":
        start_handoff(session, str(args.get("reason", "")))
        return json.dumps({"ok": True, "state": "handoff"})
    return json.dumps({"ok": False, "errors": [f"unknown tool {name!r}"]})
