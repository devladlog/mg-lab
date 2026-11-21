import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC / "tools"))


@pytest.fixture(scope="session")
def contract():
    return json.loads((SRC / "contract" / "store-statement-2025.json").read_text(encoding="utf-8"))


def render_fake_pdf(contract, path, tamper=None, blank_after_each=False):
    """SIMULATED export: a PDF drawn with reportlab from the contract. It stands in for what the service returns,
    so verify_pdf.py can be tested here. It is not a render of the .rdl."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    n_pages = len(contract["stores"]) * (2 if blank_after_each else 1)
    c = canvas.Canvas(str(path), pagesize=A4)
    page = 0
    for store in contract["stores"]:
        page += 1
        c.setFont("Helvetica", 9)
        c.drawString(54, 800, contract["title"])
        c.setFont("Helvetica-Bold", 14)
        c.drawString(54, 760, store["store"])
        y = 730
        c.setFont("Helvetica", 10)
        for col, x in zip(contract["columns"], (54, 150, 300, 400)):
            c.drawString(x, y, col)
        for m in store["months"]:
            y -= 18
            sales = m["sales_amount"]
            if tamper and tamper == (store["store"], m["month"]):
                sales = "0.01"
            for text, x in zip((m["month"], sales, m["units"], m["margin_pct"]), (54, 150, 300, 400)):
                c.drawString(x, y, text)
        c.setFont("Helvetica", 9)
        c.drawString(450, 40, f"Page {page} of {n_pages}")
        c.showPage()
        if blank_after_each:
            page += 1
            c.setFont("Helvetica", 9)
            c.drawString(450, 40, f"Page {page} of {n_pages}")
            c.showPage()
    c.save()
