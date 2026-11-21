"""Validate an extracted invoice against Contoso's expenses policy and route it: approve, review or reject.

The policy is the one indexed in episode 3 (expenses#submitting-expense-claims): a supplier invoice must show
Contoso's VAT number, the supplier's VAT number, the invoice date and the tax amount.

Routing follows Microsoft's guidance for Document Intelligence: confidence is an estimate between 0 and 1;
use it to send results either to straight-through processing or to a human, with thresholds you set from a
pilot on your own documents (the transparency note's example: >= 0.80 straight through, below that review).
The thresholds below are starting points per field, stricter for money and identifiers - tune them on real data.

Decision order matters:
  reject  - only for facts we are confident about: a confidently read customer VAT number that isn't Contoso's,
            or a duplicate (same vendor VAT + invoice number already processed)
  review  - anything uncertain: a required field missing or below its threshold, or totals that don't add up
            (which may be a reading error, not a supplier error)
  approve - everything present, confident and consistent
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .fields import Invoice

CONTOSO_VAT = "PT000000000"  # normalised form of the fictional "PT 000 000 000"
REQUIRED = ("CustomerTaxId", "VendorTaxId", "InvoiceDate", "TotalTax", "InvoiceId", "InvoiceTotal")
THRESHOLDS = {
    "InvoiceTotal": 0.90, "TotalTax": 0.90, "SubTotal": 0.85,
    "VendorTaxId": 0.90, "CustomerTaxId": 0.90, "InvoiceId": 0.85, "InvoiceDate": 0.85,
}
TOLERANCE = Decimal("0.01")


@dataclass
class Decision:
    outcome: str  # "approve" | "review" | "reject"
    reasons: list[str] = field(default_factory=list)


def normalise_tax_id(value: str | None) -> str | None:
    return re.sub(r"[^A-Z0-9]", "", value.upper()) if value else None


def invoice_key(inv: Invoice) -> tuple[str | None, str | None]:
    return normalise_tax_id(inv.value("VendorTaxId")), (inv.value("InvoiceId") or "").strip().upper() or None


def decide(inv: Invoice, seen: set[tuple[str | None, str | None]] | None = None,
           thresholds: dict[str, float] = THRESHOLDS) -> Decision:
    reject, review = [], []

    customer_vat = normalise_tax_id(inv.value("CustomerTaxId"))
    if (customer_vat and customer_vat != CONTOSO_VAT
            and inv.confidence("CustomerTaxId") >= thresholds["CustomerTaxId"]):
        reject.append(f"billed to VAT {inv.value('CustomerTaxId')}, not Contoso")
    key = invoice_key(inv)
    if seen is not None and all(key):
        if key in seen:
            reject.append(f"duplicate of invoice {key[1]} from {key[0]}")
        seen.add(key)

    for name in REQUIRED:
        if inv.value(name) in (None, ""):
            review.append(f"{name} not found")
    for name, minimum in thresholds.items():
        if inv.value(name) not in (None, "") and inv.confidence(name) < minimum:
            review.append(f"{name} confidence {inv.confidence(name):.2f} < {minimum:.2f}")

    sub, tax, total = inv.value("SubTotal"), inv.value("TotalTax"), inv.value("InvoiceTotal")
    if None not in (sub, tax, total) and abs(sub + tax - total) > TOLERANCE:
        review.append(f"subtotal {sub} + tax {tax} != total {total}")
    amounts = [i.amount for i in inv.items]
    if sub is not None and amounts and None not in amounts and abs(sum(amounts) - sub) > TOLERANCE:
        review.append(f"line items sum to {sum(amounts)}, subtotal says {sub}")
    due, issued = inv.value("DueDate"), inv.value("InvoiceDate")
    if due and issued and due < issued:
        review.append("due date before invoice date")
    if inv.currency and inv.currency != "EUR":
        review.append(f"currency {inv.currency}, expected EUR")

    if reject:
        return Decision("reject", reject + review)
    if review:
        return Decision("review", review)
    return Decision("approve", [])
