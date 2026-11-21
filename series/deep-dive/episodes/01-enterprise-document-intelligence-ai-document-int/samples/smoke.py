"""POST sample invoices to the deployed function and print the decision for each (no dependencies).

    export INVOICE_API_URL=https://<app>.azurewebsites.net/api/invoices/extract
    read -rs INVOICE_API_KEY && export INVOICE_API_KEY          # function key, never echoed
    python samples/smoke.py samples/out/*.pdf
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def post_invoice(url: str, key: str, path: Path, timeout: float = 120) -> tuple[int, dict]:
    req = urllib.request.Request(
        url, data=path.read_bytes(), method="POST",
        headers={"Content-Type": "application/pdf", "X-File-Name": path.name, "x-functions-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body or b"{}")
        except ValueError:
            return e.code, {"error": body.decode(errors="replace")[:200]}


def summary(name: str, status: int, out: dict) -> str:
    if status != 200:
        return f"{name:<28} HTTP {status}  {out.get('error', '')}"
    f = out.get("fields", {})
    line = f"{name:<28} {out['status']:<13} {f.get('InvVendor') or '-'} | {f.get('InvNumber') or '-'} | " \
           f"{f.get('InvTotal')} {f.get('InvCurrency') or ''} | conf {f.get('InvConfidence')}"
    reasons = "".join(f"\n{'':<30}- {r}" for r in out.get("reasons", []))
    return line + reasons


def main(argv: list[str]) -> int:
    url, key = os.environ.get("INVOICE_API_URL"), os.environ.get("INVOICE_API_KEY")
    if not url or not key:
        print("Set INVOICE_API_URL and INVOICE_API_KEY first.", file=sys.stderr)
        return 2
    if not argv:
        print("Usage: smoke.py FILE.pdf [FILE.pdf ...]", file=sys.stderr)
        return 2
    worst = 0
    for p in map(Path, argv):
        status, out = post_invoice(url, key, p)
        print(summary(p.name, status, out))
        worst = max(worst, 0 if status == 200 else 1)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
