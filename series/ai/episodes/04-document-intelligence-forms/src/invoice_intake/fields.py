"""Turn a prebuilt-invoice analyze result into a typed Invoice, keeping each field's confidence.

Works on the REST JSON shape (camelCase keys), which is also how the SDK's AnalyzeResult behaves as a mapping,
so the same code reads a live result and a saved `analyzeResult` JSON file.

Field names and types follow the invoice model schema for API 2024-11-30 (v4.0 GA):
InvoiceId/VendorName/VendorTaxId/CustomerTaxId/CustomerName are `string`, InvoiceDate/DueDate are `date`,
SubTotal/TotalTax/InvoiceTotal are `currency` ({amount, currencyCode, currencySymbol}), Items is an `array` of
`object` with Description (string), Quantity (number), UnitPrice and Amount (currency).
Learn: not every field returns a confidence; a missing confidence is treated as 0 here (never auto-approved).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

HEADER_FIELDS = ("InvoiceId", "InvoiceDate", "DueDate", "VendorName", "VendorTaxId", "CustomerName", "CustomerTaxId",
                 "SubTotal", "TotalTax", "InvoiceTotal")


@dataclass
class Extracted:
    value: Any
    confidence: float
    content: str | None = None


@dataclass
class LineItem:
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass
class Invoice:
    fields: dict[str, Extracted]
    items: list[LineItem] = field(default_factory=list)
    currency: str | None = None
    doc_confidence: float = 0.0

    def value(self, name: str):
        f = self.fields.get(name)
        return f.value if f else None

    def confidence(self, name: str) -> float:
        f = self.fields.get(name)
        return f.confidence if f else 0.0


def _money(amount: Any) -> Decimal | None:
    return None if amount is None else Decimal(str(amount)).quantize(Decimal("0.01"))


def field_value(f: Mapping[str, Any]) -> tuple[Any, str | None]:
    """Typed value of one DocumentField, plus the currency code for currency fields."""
    t = f.get("type")
    if t == "currency":
        cur = f.get("valueCurrency") or {}
        return _money(cur.get("amount")), cur.get("currencyCode")
    if t == "date":
        v = f.get("valueDate")
        return (date.fromisoformat(v) if v else None), None
    if t == "number":
        v = f.get("valueNumber")
        return (None if v is None else Decimal(str(v))), None
    if t == "integer":
        return f.get("valueInteger"), None
    if t == "string":
        return f.get("valueString"), None
    if t == "address":
        return f.get("valueAddress"), None
    return f.get("content"), None


def to_invoice(analyze_result: Mapping[str, Any]) -> Invoice:
    documents = analyze_result.get("documents") or []
    if not documents:
        raise ValueError("no document found: the model didn't recognise an invoice in this file")
    doc = documents[0]
    raw = doc.get("fields") or {}
    fields: dict[str, Extracted] = {}
    currency = None
    for name in HEADER_FIELDS:
        f = raw.get(name)
        if not f:
            continue
        value, code = field_value(f)
        currency = currency or code
        fields[name] = Extracted(value, float(f.get("confidence") or 0.0), f.get("content"))
    items = []
    for row in (raw.get("Items") or {}).get("valueArray") or []:
        obj = row.get("valueObject") or {}

        def get(key):
            return field_value(obj[key])[0] if key in obj else None

        items.append(LineItem(get("Description"), get("Quantity"), get("UnitPrice"), get("Amount")))
    return Invoice(fields, items, currency, float(doc.get("confidence") or 0.0))
