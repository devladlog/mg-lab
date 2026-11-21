"""Invoice review queue and AP policy: the business rules live here, in code, not in the prompt.

The agent can *ask* to approve anything. Whether an approval is allowed is decided by `InvoiceStore.approve()`,
after a person has confirmed the call (see agent.py). Two independent gates: a human and the code.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
APPROVAL_LIMIT = Decimal("5000.00")  # policy: AP staff approve up to EUR 5,000.00


def _reason_kinds(inv: dict) -> set[str]:
    """Review reasons are written as '<kind>: <detail>' by the episode 4 intake step."""
    return {r.split(":", 1)[0].strip() for r in inv.get("review_reasons", [])}


@dataclass
class InvoiceStore:
    invoices: dict[str, dict]
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | str = DATA / "invoices.json") -> "InvoiceStore":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({i["id"]: copy.deepcopy(i) for i in raw["invoices"]})

    def queue(self) -> list[dict]:
        """Short summaries of the invoices waiting for review (what list_review_queue returns)."""
        return [{"id": i["id"], "vendor": i["vendor"], "total": i["total"], "currency": i["currency"],
                 "review_reasons": i["review_reasons"]}
                for i in self.invoices.values() if i["status"] == "review"]

    def get(self, invoice_id: str) -> dict | None:
        inv = self.invoices.get(invoice_id.strip().upper())
        return copy.deepcopy(inv) if inv else None

    def approve(self, invoice_id: str, note: str, approver: str) -> dict:
        """Approve one invoice if, and only if, the policy allows it. Idempotent."""
        inv = self.invoices.get(invoice_id.strip().upper())
        if inv is None:
            return {"ok": False, "invoice_id": invoice_id, "error": "not_found"}
        if inv["status"] == "approved":
            return {"ok": True, "invoice_id": inv["id"], "message": "already approved", "approved_by": inv["approved_by"]}
        refusal = self._refusal(inv, note)
        if refusal:
            self.events.append({"invoice_id": inv["id"], "action": "approve_refused", "reason": refusal})
            return {"ok": False, "invoice_id": inv["id"], "error": "policy", "message": refusal}
        inv.update(status="approved", approved_by=approver, approval_note=note.strip(),
                   approved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.events.append({"invoice_id": inv["id"], "action": "approved", "by": approver})
        return {"ok": True, "invoice_id": inv["id"], "message": "approved", "approved_by": approver}

    @staticmethod
    def _refusal(inv: dict, note: str) -> str | None:
        kinds = _reason_kinds(inv)
        if inv["status"] != "review":
            return f"status is {inv['status']}; rejected invoices are not reopened from the review queue"
        if "arithmetic" in kinds:
            return "totals do not add up; request a corrected invoice from the supplier"
        if Decimal(inv["total"]) > APPROVAL_LIMIT:
            return f"total {inv['total']} is above the EUR {APPROVAL_LIMIT} limit; the finance manager approves"
        if "new-supplier" in kinds:
            return "first invoice from a new VAT number; procurement must verify the supplier first"
        if not note or not note.strip():
            return "an approval note is required"
        return None


# --- policy -------------------------------------------------------------------------------------------------------

_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def load_policy(path: Path | str = DATA / "policy.md") -> dict[str, str]:
    """Second-level headings -> section text."""
    sections: dict[str, str] = {}
    current = None
    for line in _COMMENT.sub("", Path(path).read_text(encoding="utf-8")).splitlines():
        m = _HEADING.match(line)
        if m:
            current = m.group(1)
            sections[current] = ""
        elif current:
            sections[current] = (sections[current] + " " + line.strip()).strip()
    return sections


def lookup_policy(sections: dict[str, str], topic: str) -> list[dict]:
    """Sections sharing a word stem with the topic (words of 4+ letters, first 5 letters compared).

    Deliberately simple: the point of the episode is the agent loop, not retrieval (that was episode 3).
    """
    def stems(text: str) -> set[str]:
        return {w[:5] for w in re.findall(r"[a-z]{4,}", text.lower())}

    wanted = stems(topic)
    return [{"section": h, "text": t} for h, t in sections.items() if wanted & stems(h + " " + t)]
