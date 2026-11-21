"""Writes the fictional sample invoices in src/samples/ (reportlab for PDFs, Pillow for images).

Everything is made up: Adatum Office Supplies invoicing Contoso Ltd. Re-running overwrites the files.
  invoice-clean.pdf       one A4 page, a text layer, total = subtotal + tax
  invoice-two-in-one.pdf  3 pages: invoice A on page 1, invoice B on pages 2-3 (shows the Pages parameter)
  invoice-mismatch.pdf    the total doesn't equal subtotal + tax (the model reads it right; the invoice is wrong)
  invoice-oversize.pdf    one page of 20 x 20 inches: over the 17 x 17 inch limit
  invoice-scan.png        the clean invoice drawn as a low resolution, noisy image (no text layer)
  invoice-tiny.png        40 x 40 pixels: under the 50 x 50 minimum
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "samples"
VENDOR = ["Adatum Office Supplies", "12 Example Street", "Sampletown 00000"]
CUSTOMER = ["Contoso Ltd", "Accounts Payable", "1 Demo Road, Sampletown 00000"]


def _page(c: canvas.Canvas, inv: dict, page_label: str = "") -> None:
    w, h = c._pagesize
    y = h - 60
    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, y, "INVOICE")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(VENDOR):
        c.drawString(w - 220, y - i * 13, line)
    y -= 40
    if page_label:
        c.drawString(50, y, page_label)
        y -= 16
    c.drawString(50, y, f"Invoice No: {inv['id']}")
    c.drawString(50, y - 14, f"Invoice Date: {inv['date']}")
    c.drawString(50, y - 28, f"Due Date: {inv['due']}")
    c.drawString(50, y - 42, f"Purchase Order: {inv['po']}")
    c.drawString(300, y, "Bill To:")
    for i, line in enumerate(CUSTOMER):
        c.drawString(300, y - 14 - i * 13, line)
    y -= 100
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Description")
    c.drawString(330, y, "Qty")
    c.drawString(390, y, "Unit price")
    c.drawString(480, y, "Amount")
    c.setFont("Helvetica", 10)
    for desc, qty, price in inv["items"]:
        y -= 16
        c.drawString(50, y, desc)
        c.drawString(330, y, str(qty))
        c.drawRightString(450, y, f"{price:,.2f}")
        c.drawRightString(540, y, f"{qty * price:,.2f}")
    sub = sum(q * p for _, q, p in inv["items"])
    y -= 30
    c.drawString(390, y, "Subtotal")
    c.drawRightString(540, y, f"{sub:,.2f}")
    c.drawString(390, y - 14, "Tax (20%)")
    c.drawRightString(540, y - 14, f"{inv['tax']:,.2f}")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(390, y - 32, "Total due")
    c.drawRightString(540, y - 32, f"{inv['total']:,.2f}")


def invoice(inv_id: str, date: str, due: str, po: str, items: list, total: float | None = None) -> dict:
    sub = sum(q * p for _, q, p in items)
    tax = round(sub * 0.2, 2)
    return {"id": inv_id, "date": date, "due": due, "po": po, "items": items, "tax": tax,
            "total": round(sub + tax, 2) if total is None else total}


CLEAN = invoice("INV-2026-0412", "2026-11-02", "2026-12-02", "PO-7731",
                [("Ergonomic keyboard", 5, 49.90), ("USB-C dock", 2, 129.00), ("Monitor arm", 3, 38.50)])
SECOND = invoice("INV-2026-0413", "2026-11-03", "2026-12-03", "PO-7732",
                 [("Standing desk frame", 4, 310.00), ("Desk top 160 cm", 4, 120.00), ("Cable tray", 4, 18.75),
                  ("Delivery", 1, 45.00)])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, inv in (("invoice-clean.pdf", CLEAN),
                      ("invoice-mismatch.pdf", invoice("INV-2026-0414", "2026-11-04", "2026-12-04", "PO-7733",
                                                       [("Whiteboard 120 cm", 2, 85.00)], total=250.00))):
        c = canvas.Canvas(str(OUT / name), pagesize=A4, invariant=1)
        _page(c, inv)
        c.save()
    c = canvas.Canvas(str(OUT / "invoice-two-in-one.pdf"), pagesize=A4, invariant=1)
    _page(c, CLEAN)
    c.showPage()
    _page(c, SECOND)
    c.showPage()
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "INVOICE (continued)")
    c.drawString(50, 764, f"Invoice No: {SECOND['id']}   Page 2 of 2")
    c.drawString(50, 740, "Payment: bank transfer within 30 days. Thank you for your business.")
    c.save()
    c = canvas.Canvas(str(OUT / "invoice-oversize.pdf"), pagesize=(20 * 72, 20 * 72), invariant=1)
    _page(c, CLEAN)
    c.save()

    rng = random.Random(7)   # repeatable noise
    img = Image.new("L", (620, 800), 245)
    d = ImageDraw.Draw(img)
    d.text((30, 30), "INVOICE", fill=40)
    d.text((30, 70), f"Invoice No: {CLEAN['id']}", fill=60)
    d.text((30, 90), f"Invoice Date: {CLEAN['date']}", fill=60)
    d.text((30, 110), "Adatum Office Supplies", fill=60)
    d.text((30, 700), f"Total due {CLEAN['total']:,.2f}", fill=60)
    for _ in range(2500):
        d.point((rng.randrange(620), rng.randrange(800)), fill=rng.randrange(120, 230))
    img.rotate(1.5, fillcolor=245).filter(ImageFilter.GaussianBlur(1.1)).save(OUT / "invoice-scan.png")
    Image.new("RGB", (40, 40), (255, 255, 255)).save(OUT / "invoice-tiny.png")
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
