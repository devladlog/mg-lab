"""Analyze invoices with prebuilt-invoice, then validate and route each one.

    PYTHONPATH=src python -m invoice_intake.process samples/0*.png --endpoint https://<resource>.cognitiveservices.azure.com \
        --save-json results/
    PYTHONPATH=src python -m invoice_intake.process --replay results/*.json      # offline, from saved results

Keyless: DefaultAzureCredential. Learn: Microsoft Entra authentication needs the resource's custom subdomain
endpoint (regional endpoints don't support it) and the caller needs the "Cognitive Services User" role.
Analyze is a long-running operation: POST ...:analyze returns 202 + Operation-Location, the SDK poller GETs it
until the status is succeeded or failed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .decide import Decision, decide
from .fields import Invoice, to_invoice

API_VERSION = "2024-11-30"  # v4.0 GA, what azure-ai-documentintelligence 1.0.x targets
MODEL_ID = "prebuilt-invoice"


def make_client(endpoint: str, credential=None, **kwargs):
    from azure.ai.documentintelligence import DocumentIntelligenceClient

    if credential is None:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
    return DocumentIntelligenceClient(endpoint, credential, **kwargs)


def analyze_file(client, path: str | Path, *, model_id: str = MODEL_ID, locale: str = "en-US",
                 polling_interval: float | None = None) -> dict[str, Any]:
    """Send the file bytes, wait for the operation, return the analyze result as a REST-shaped dict."""
    kwargs = {"locale": locale}
    if polling_interval is not None:
        kwargs["polling_interval"] = polling_interval
    with open(path, "rb") as f:
        poller = client.begin_analyze_document(model_id, f, **kwargs)
    result = poller.result()
    return result.as_dict() if hasattr(result, "as_dict") else dict(result)


def route_all(results: Iterable[tuple[str, dict[str, Any]]]) -> list[tuple[str, Invoice | None, Decision]]:
    """Validate and route in order; the `seen` set makes the duplicate check work across the batch."""
    seen: set = set()
    rows = []
    for name, result in results:
        try:
            inv = to_invoice(result)
        except ValueError as e:
            rows.append((name, None, Decision("review", [str(e)])))
            continue
        rows.append((name, inv, decide(inv, seen)))
    return rows


def report(rows) -> str:
    lines = [f"{'file':32} {'vendor':26} {'total':>10} {'conf':>5}  decision  reasons", "-" * 110]
    for name, inv, d in rows:
        vendor = (inv.value("VendorName") or "?")[:26] if inv else "?"
        total = inv.value("InvoiceTotal") if inv else None
        conf = f"{inv.confidence('InvoiceTotal'):.2f}" if inv else "-"
        lines.append(f"{name[:32]:32} {vendor:26} {str(total or '?'):>10} {conf:>5}  {d.outcome:8}  {'; '.join(d.reasons) or '-'}")
    counts = {k: sum(1 for *_, d in rows if d.outcome == k) for k in ("approve", "review", "reject")}
    lines.append("-" * 110)
    lines.append("  ".join(f"{k}: {v}" for k, v in counts.items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="invoice_intake.process", description="Extract, validate and route invoices.")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--endpoint", help="https://<custom-subdomain>.cognitiveservices.azure.com")
    ap.add_argument("--replay", nargs="*", help="saved analyzeResult JSON files instead of calling the service")
    ap.add_argument("--save-json", help="folder to save each analyze result (for replay and for tests)")
    ap.add_argument("--locale", default="en-US")
    a = ap.parse_args(argv)
    if a.replay:
        results = [(Path(p).name, json.loads(Path(p).read_text(encoding="utf-8"))) for p in a.replay]
    else:
        if not (a.endpoint and a.files):
            ap.error("give files and --endpoint, or --replay")
        client = make_client(a.endpoint)
        results = []
        for p in sorted(a.files):
            result = analyze_file(client, p, locale=a.locale)
            if a.save_json:
                out = Path(a.save_json)
                out.mkdir(parents=True, exist_ok=True)
                (out / (Path(p).stem + ".json")).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
            results.append((Path(p).name, result))
    print(report(route_all(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
