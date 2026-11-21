"""Synthetic analyze results in the REST shape of prebuilt-invoice (API 2024-11-30).

These are NOT captured from the service: they're built from the sample invoices' own data, as if the model had
read every field correctly with the given confidence, so the mapping and routing rules can be tested exactly.
Field types and value keys follow the invoice schema (string/date/currency/number/array/object).
The live demo saves real results with `process --save-json`; those can be dropped in for replay.
"""
from __future__ import annotations

from invoice_intake.samples import SAMPLES, SampleInvoice


def _box(x, y, w=300, h=30):
    return [{"pageNumber": 1, "polygon": [x, y, x + w, y, x + w, y + h, x, y + h]}]


def _str(v, conf, box):
    return {"type": "string", "valueString": v, "content": v, "confidence": conf, "boundingRegions": box}


def _date(v, conf, box):
    return {"type": "date", "valueDate": v, "content": v, "confidence": conf, "boundingRegions": box}


def _cur(amount, conf, box):
    return {"type": "currency", "content": f"{amount:,.2f} EUR", "confidence": conf, "boundingRegions": box,
            "valueCurrency": {"amount": float(amount), "currencyCode": "EUR", "currencySymbol": "EUR"}}


def analyze_result(sample: SampleInvoice, conf: float = 0.95, overrides: dict | None = None,
                   drop: tuple[str, ...] = ()) -> dict:
    s = sample
    fields = {
        "VendorName": _str(s.vendor, conf, _box(90, 90, 600, 50)),
        "VendorTaxId": _str(s.vendor_vat, conf, _box(250, 228, 230)),
        "InvoiceId": _str(s.invoice_id, conf, _box(1000, 180, 150)),
        "InvoiceDate": _date(s.invoice_date, conf, _box(1000, 216, 150)),
        "DueDate": _date(s.due_date, conf, _box(1000, 252, 150)),
        "CustomerName": _str(s.customer, conf, _box(90, 460, 300)),
        "CustomerTaxId": _str(s.customer_vat, conf, _box(250, 532, 230)),
        "SubTotal": _cur(s.subtotal, conf, _box(980, 820, 170)),
        "TotalTax": _cur(s.tax, conf, _box(980, 866, 170)),
        "InvoiceTotal": _cur(s.total, conf, _box(980, 912, 170)),
        "Items": {"type": "array", "valueArray": [
            {"type": "object", "confidence": conf, "valueObject": {
                "Description": _str(l.description, conf, None),
                "Quantity": {"type": "number", "valueNumber": l.quantity, "confidence": conf},
                "UnitPrice": _cur(l.unit_price, conf, None),
                "Amount": _cur(l.amount, conf, None),
            }} for l in s.lines]},
    }
    for name, c in (overrides or {}).items():
        fields[name]["confidence"] = c
    for name in drop:
        fields.pop(name, None)
    return {
        "apiVersion": "2024-11-30", "modelId": "prebuilt-invoice", "stringIndexType": "textElements",
        "content": f"{s.vendor}\nINVOICE ...",
        "pages": [{"pageNumber": 1, "unit": "pixel", "width": 1240, "height": 1754}],
        "documents": [{"docType": "invoice", "confidence": 1.0, "fields": fields}],
    }


def sample(prefix: str) -> SampleInvoice:
    return next(s for s in SAMPLES if s.file.startswith(prefix))
