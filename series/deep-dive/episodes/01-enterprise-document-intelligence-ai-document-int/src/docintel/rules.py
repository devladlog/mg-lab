"""Routing rules: is this invoice Ready, does it need a human, or is it not an invoice at all?

The model gives values and confidence. Whether 0.78 is "good enough" is a business decision, so the
thresholds live in a Policy you can change per environment (app settings), not in the model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from .contract import NEEDS_REVIEW, READY, REJECTED
from .mapping import REQUIRED, Extracted, to_columns


@dataclass(frozen=True)
class Policy:
    min_confidence: float = 0.80          # per required field
    approval_limit: float = 10_000.0      # above this a person always looks at it
    allowed_currencies: tuple[str, ...] = ("EUR", "GBP", "USD")
    total_tolerance: float = 0.01         # subtotal + tax vs total, in currency units

    @classmethod
    def from_env(cls, env=os.environ) -> "Policy":
        d = cls()
        return cls(
            min_confidence=float(env.get("MIN_CONFIDENCE", d.min_confidence)),
            approval_limit=float(env.get("APPROVAL_LIMIT", d.approval_limit)),
            allowed_currencies=tuple(
                c.strip().upper() for c in env.get("ALLOWED_CURRENCIES", ",".join(d.allowed_currencies)).split(",") if c.strip()
            ),
            total_tolerance=float(env.get("TOTAL_TOLERANCE", d.total_tolerance)),
        )


@dataclass
class Decision:
    status: str
    reasons: list[str]
    columns: dict


def decide(x: Extracted, policy: Policy = Policy()) -> Decision:
    cols = to_columns(x)
    reasons: list[str] = []

    if x.document_count == 0:
        return _done(REJECTED, ["No invoice found in the file."], cols)
    if x.document_count > 1:
        reasons.append(f"{x.document_count} invoices in one file; only the first was read.")

    for f in REQUIRED:
        if f not in x.values:
            reasons.append(f"Missing {f}.")
        elif x.confidence.get(f, 0.0) < policy.min_confidence:
            reasons.append(f"Low confidence on {f} ({x.confidence[f]:.2f} < {policy.min_confidence:.2f}).")

    total, sub, tax = cols["InvTotal"], cols["InvSubTotal"], cols["InvTax"]
    if total is not None and sub is not None and tax is not None:
        if abs((sub + tax) - total) > policy.total_tolerance:
            reasons.append(f"Subtotal + tax ({sub + tax:.2f}) does not match total ({total:.2f}).")

    if total is not None:
        if not cols["InvCurrency"]:
            reasons.append("Currency is ambiguous or missing.")
        elif cols["InvCurrency"] not in policy.allowed_currencies:
            reasons.append(f"Currency {cols['InvCurrency']} is not accepted.")
        if total > policy.approval_limit:
            reasons.append(f"Total above the approval limit ({policy.approval_limit:,.0f}).")
        if total <= 0:
            reasons.append("Total is zero or negative (credit note?).")

    inv_date, due = _date(cols["InvDate"]), _date(cols["InvDueDate"])
    if inv_date and due and due < inv_date:
        reasons.append("Due date is before the invoice date.")

    return _done(NEEDS_REVIEW if reasons else READY, reasons, cols)


def _date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _done(status: str, reasons: list[str], cols: dict) -> Decision:
    cols = dict(cols, InvStatus=status, InvReasons="\n".join(reasons))
    return Decision(status, reasons, cols)
