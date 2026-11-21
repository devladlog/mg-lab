"""Triage of one extraction: auto-post, review or reject.

The input is a dict with the columns the flow writes to the staging list "Invoice Extractions": the value
of each field Learn lists for the model (InvoiceId, VendorName, InvoiceDate, DueDate, SubTotal, TotalTax,
InvoiceTotal) and, next to each one, its confidence score (InvoiceIdConf ...), a number from 0 (low) to 1
(high) per Learn. The thresholds are OUR choices, not Microsoft's: Learn's examples only show 0.65 as a
point where a second model is tried.

The same rules are written as flow expressions in tools/build_solution.py; tests/test_flow_parity.py runs
both on the same cases and requires the same decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

EPS = 1e-6   # binary floating point: 100 + 20 - 120.01 is 0.010000000000005 and must still count as one cent
REQUIRED = ("InvoiceId", "VendorName", "InvoiceDate", "InvoiceTotal")
AUTO, REVIEW, REJECT = "auto-post", "review", "reject"


@dataclass
class Config:
    min_confidence: float = 0.80     # every required field must reach it to be posted without a person
    amount_limit: float = 5000.0     # above this a person looks, however sure the model is
    tolerance: float = 0.01          # SubTotal + TotalTax may differ from InvoiceTotal by this much
    max_age_days: int = 365          # invoice dates older than this are suspicious


@dataclass
class Reason:
    code: str
    text: str


@dataclass
class Decision:
    action: str
    reasons: list[Reason] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return [r.code for r in self.reasons]


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v) -> float | None:
    if _blank(v):
        return None
    return float(v)


def _day(v) -> date | None:
    if _blank(v):
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()


def dup_key(vendor, invoice_id) -> tuple[str, str]:
    """Exact match after trim and lower case. INV-001 and INV001 are NOT the same here (see README)."""
    return (str(vendor or "").strip().lower(), str(invoice_id or "").strip().lower())


def decide(x: dict, cfg: Config | None = None, today: date | None = None,
           known: set[tuple[str, str]] | None = None) -> Decision:
    cfg = cfg or Config()
    today = today or date.today()
    known = known or set()
    d = Decision(AUTO)

    missing = [f for f in REQUIRED if _blank(x.get(f))]
    if len(missing) >= 3 and all(_blank(x.get(f)) for f in ("InvoiceId", "VendorName", "InvoiceTotal")):
        return Decision(REJECT, [Reason("NOT_INVOICE", "no invoice id, vendor or total: probably not an invoice")])
    if not _blank(x.get("InvoiceId")) and dup_key(x.get("VendorName"), x.get("InvoiceId")) in known:
        return Decision(REJECT, [Reason("DUPLICATE", f"{x.get('VendorName')} {x.get('InvoiceId')} is already in the Invoices list")])

    if missing:
        d.reasons.append(Reason("MISSING", "missing: " + ", ".join(missing)))
    low = [f for f in REQUIRED if not _blank(x.get(f)) and (_num(x.get(f + "Conf")) or 0.0) < cfg.min_confidence]
    if low:
        d.reasons.append(Reason("LOWCONF", f"confidence under {cfg.min_confidence:g}: " + ", ".join(low)))

    sub, tax, total = _num(x.get("SubTotal")), _num(x.get("TotalTax")), _num(x.get("InvoiceTotal"))
    if sub is not None and tax is not None and total is not None and abs(sub + tax - total) > cfg.tolerance + EPS:
        d.reasons.append(Reason("MISMATCH", f"subtotal {sub:g} + tax {tax:g} is not total {total:g}"))
    if total is not None and total > cfg.amount_limit:
        d.reasons.append(Reason("OVERLIMIT", f"total {total:g} is over the limit {cfg.amount_limit:g}"))

    inv, due = _day(x.get("InvoiceDate")), _day(x.get("DueDate"))
    if inv is not None and (inv > today + timedelta(days=1) or inv < today - timedelta(days=cfg.max_age_days)):
        d.reasons.append(Reason("DATE", f"invoice date {inv} is in the future or older than {cfg.max_age_days} days"))
    elif inv is not None and due is not None and due < inv:
        d.reasons.append(Reason("DATE", f"due date {due} is before the invoice date {inv}"))

    if d.reasons:
        d.action = REVIEW
    return d
