"""Turn a Document Intelligence prebuilt-invoice AnalyzeResult (REST/JSON shape) into library columns.

Works on the plain dict (``AnalyzeResult.as_dict()``), so it is testable without the service.
Field names come from the v4.0 invoice model (VendorName, InvoiceId, InvoiceDate, ... InvoiceTotal).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Fields we require before an invoice can be "Ready". Their confidence decides the routing.
REQUIRED = ("VendorName", "InvoiceId", "InvoiceDate", "InvoiceTotal")

# Only unambiguous symbols. "$" is used by many currencies, so it maps to nothing (-> human review).
SYMBOL_TO_CODE = {"€": "EUR", "£": "GBP"}


@dataclass
class Extracted:
    """Values + per-field confidence for one invoice document."""
    values: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    doc_type: str | None = None
    doc_confidence: float | None = None
    page_count: int = 0
    document_count: int = 0

    @property
    def min_required_confidence(self) -> float:
        """Lowest confidence among required fields; a missing required field counts as 0."""
        return min((self.confidence.get(f, 0.0) for f in REQUIRED), default=0.0)


def _value(f: dict) -> Any:
    """Read the typed value of a DocumentField (string, date, number, currency)."""
    t = f.get("type")
    if t == "string":
        return f.get("valueString")
    if t == "date":
        return f.get("valueDate")
    if t == "number":
        return f.get("valueNumber")
    if t == "currency":
        cur = f.get("valueCurrency") or {}
        code = cur.get("currencyCode") or SYMBOL_TO_CODE.get((cur.get("currencySymbol") or "").strip())
        return {"amount": cur.get("amount"), "currency": code}
    # Fall back to the raw text the model read.
    return f.get("content")


def extract(result: dict) -> Extracted:
    """Map the first invoice in the result. Several documents in one file are flagged by the rules."""
    docs = result.get("documents") or []
    out = Extracted(page_count=len(result.get("pages") or []), document_count=len(docs))
    if not docs:
        return out
    doc = docs[0]
    out.doc_type = doc.get("docType")
    out.doc_confidence = doc.get("confidence")
    for name, f in (doc.get("fields") or {}).items():
        if not isinstance(f, dict):
            continue
        v = _value(f)
        if v in (None, "") or (isinstance(v, dict) and v.get("amount") is None):
            continue
        out.values[name] = v
        if f.get("confidence") is not None:
            out.confidence[name] = float(f["confidence"])
    return out


def dedup_key(vendor: str | None, invoice_id: str | None) -> str:
    """Same vendor + same invoice number => same key, whatever the spacing or case on the PDF."""
    v = re.sub(r"[^a-z0-9]", "", (vendor or "").lower())
    i = re.sub(r"[^A-Z0-9]", "", (invoice_id or "").upper())
    return f"{v}|{i}" if v and i else ""


def _amount(values: dict, name: str):
    v = values.get(name)
    return v.get("amount") if isinstance(v, dict) else None


def to_columns(x: Extracted) -> dict[str, Any]:
    """Library column values (internal names from columns.json). Status/reasons are added by the rules."""
    vals = x.values
    total = vals.get("InvoiceTotal") if isinstance(vals.get("InvoiceTotal"), dict) else {}
    return {
        "InvVendor": vals.get("VendorName"),
        "InvNumber": vals.get("InvoiceId"),
        "InvDate": vals.get("InvoiceDate"),
        "InvDueDate": vals.get("DueDate"),
        "InvPO": vals.get("PurchaseOrder"),
        "InvSubTotal": _amount(vals, "SubTotal"),
        "InvTax": _amount(vals, "TotalTax"),
        "InvTotal": total.get("amount"),
        "InvCurrency": total.get("currency"),
        "InvConfidence": round(x.min_required_confidence, 3),
        "InvDedupKey": dedup_key(vals.get("VendorName"), vals.get("InvoiceId")),
    }
