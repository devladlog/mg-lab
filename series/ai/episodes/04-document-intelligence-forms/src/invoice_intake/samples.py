"""Render fictional supplier invoices (PNG) for the demo, so no real document ever goes near the service.

    PYTHONPATH=src python -m invoice_intake.samples --out samples

Each sample is designed to exercise one path of the intake rules:
  01-fabrikam-clean          everything right                       -> expected: approve
  02-northwind-bad-total     subtotal + VAT != printed total        -> expected: review
  03-tailspin-wrong-customer billed to another company's VAT number -> expected: reject
  04-adventure-works-faded   faded, slightly rotated "scan"         -> expected: depends on live confidence
  05-fabrikam-duplicate      same vendor + invoice number as 01     -> expected: reject (duplicate)
plus contoso-expenses-policy.png, a page of the expenses policy for the layout-to-Markdown step.

Learn input requirements (prebuilt models): JPEG/PNG/BMP/TIFF/HEIF or PDF; images between 50x50 and
10,000x10,000 pixels; free tier (F0) files up to 4 MB; text at least ~12 px high for a 1024x768 image. The
renderer stays well inside those limits (1240x1754, A4 at 150 dpi, fonts >= 22 px).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

CONTOSO_VAT = "PT 000 000 000"  # fictional; zero identifier on purpose
WIDTH, HEIGHT = 1240, 1754  # A4 portrait at 150 dpi


@dataclass
class Line:
    description: str
    quantity: int
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class SampleInvoice:
    file: str
    vendor: str
    vendor_address: list[str]
    vendor_vat: str
    invoice_id: str
    invoice_date: str
    due_date: str
    customer: str
    customer_vat: str
    lines: list[Line]
    vat_rate: Decimal = Decimal("0.23")
    printed_total_override: Decimal | None = None  # to print a wrong total on purpose
    faded: bool = False
    expected: str = "approve"
    notes: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((l.amount for l in self.lines), Decimal("0"))

    @property
    def tax(self) -> Decimal:
        return (self.subtotal * self.vat_rate).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return self.printed_total_override if self.printed_total_override is not None else self.subtotal + self.tax


SAMPLES = [
    SampleInvoice("01-fabrikam-clean.png", "Fabrikam Office Supplies", ["Rua Exemplo 10", "1000-000 Lisboa"],
                  "PT 111 111 111", "FAB-2026-0412", "2026-11-02", "2026-12-02", "Contoso Ltd", CONTOSO_VAT,
                  [Line("Ergonomic office chair", 2, Decimal("189.00")), Line("Monitor arm", 2, Decimal("45.50"))]),
    SampleInvoice("02-northwind-bad-total.png", "Northwind Catering", ["Avenida Ficticia 22", "4000-000 Porto"],
                  "PT 222 222 222", "NW-88731", "2026-11-05", "2026-11-20", "Contoso Ltd", CONTOSO_VAT,
                  [Line("Team lunch, 12 people", 12, Decimal("14.00")), Line("Coffee service", 1, Decimal("32.00"))],
                  printed_total_override=Decimal("256.00"), expected="review"),
    SampleInvoice("03-tailspin-wrong-customer.png", "Tailspin Print Shop", ["Travessa Modelo 3", "3000-000 Coimbra"],
                  "PT 333 333 333", "TS-1093", "2026-11-06", "2026-12-06", "Contoso Holdings", "PT 999 000 999",
                  [Line("Business cards, 500 pcs", 4, Decimal("38.00"))], expected="reject"),
    SampleInvoice("04-adventure-works-faded.png", "Adventure Works Travel", ["Largo Inventado 7", "8000-000 Faro"],
                  "PT 444 444 444", "AW-55120", "2026-11-08", "2026-12-08", "Contoso Ltd", CONTOSO_VAT,
                  [Line("Train tickets Lisboa-Porto", 3, Decimal("31.40")), Line("Booking fee", 1, Decimal("5.00"))],
                  faded=True, expected="depends on live confidence"),
    SampleInvoice("05-fabrikam-duplicate.png", "Fabrikam Office Supplies", ["Rua Exemplo 10", "1000-000 Lisboa"],
                  "PT 111 111 111", "FAB-2026-0412", "2026-11-02", "2026-12-02", "Contoso Ltd", CONTOSO_VAT,
                  [Line("Ergonomic office chair", 2, Decimal("189.00")), Line("Monitor arm", 2, Decimal("45.50"))],
                  expected="reject"),
]


def _font(size: int, bold: bool = False):
    # Pillow >= 10.1 ships a scalable default font; good enough for OCR and needs no font files.
    return ImageFont.load_default(size=size)


def money(x: Decimal) -> str:
    return f"{x:,.2f} EUR"


def render_invoice(s: SampleInvoice) -> Image.Image:
    im = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(im)
    x0, y = 90, 90
    d.text((x0, y), s.vendor, font=_font(44), fill="black")
    for i, line in enumerate(s.vendor_address + [f"VAT number: {s.vendor_vat}"]):
        d.text((x0, y + 70 + i * 34), line, font=_font(26), fill="black")
    d.text((WIDTH - 90, y), "INVOICE", font=_font(56), fill="black", anchor="ra")
    meta = [("Invoice number", s.invoice_id), ("Invoice date", s.invoice_date), ("Due date", s.due_date)]
    for i, (k, v) in enumerate(meta):
        d.text((WIDTH - 420, y + 90 + i * 36), f"{k}:", font=_font(26), fill="black")
        d.text((WIDTH - 90, y + 90 + i * 36), v, font=_font(26), fill="black", anchor="ra")
    y = 420
    d.text((x0, y), "Bill to:", font=_font(28), fill="black")
    d.text((x0, y + 40), s.customer, font=_font(28), fill="black")
    d.text((x0, y + 76), "Avenida da Demo 1, 1100-000 Lisboa", font=_font(26), fill="black")
    d.text((x0, y + 112), f"VAT number: {s.customer_vat}", font=_font(26), fill="black")
    y = 640
    cols = [x0, 700, 860, WIDTH - 90]
    d.line((x0, y - 12, WIDTH - 90, y - 12), fill="black", width=2)
    for text, x, anchor in (("Description", cols[0], "la"), ("Qty", cols[1], "ra"), ("Unit price", cols[2] + 120, "ra"),
                            ("Amount", cols[3], "ra")):
        d.text((x, y), text, font=_font(26), fill="black", anchor=anchor)
    d.line((x0, y + 40, WIDTH - 90, y + 40), fill="black", width=2)
    y += 60
    for line in s.lines:
        d.text((cols[0], y), line.description, font=_font(26), fill="black")
        d.text((cols[1], y), str(line.quantity), font=_font(26), fill="black", anchor="ra")
        d.text((cols[2] + 120, y), f"{line.unit_price:,.2f}", font=_font(26), fill="black", anchor="ra")
        d.text((cols[3], y), f"{line.amount:,.2f}", font=_font(26), fill="black", anchor="ra")
        y += 44
    y += 30
    d.line((700, y - 10, WIDTH - 90, y - 10), fill="black", width=2)
    for k, v in (("Subtotal", s.subtotal), (f"VAT {int(s.vat_rate * 100)}%", s.tax), ("Total", s.total)):
        d.text((860, y), k, font=_font(28), fill="black", anchor="ra")
        d.text((WIDTH - 90, y), money(v), font=_font(28), fill="black", anchor="ra")
        y += 46
    d.text((x0, HEIGHT - 160), "Payment terms: 30 days. Fictional document for a demo - not a real invoice.",
           font=_font(22), fill="black")
    if s.faded:
        im = ImageEnhance.Contrast(im).enhance(0.35)
        im = im.rotate(1.2, expand=False, fillcolor="white", resample=Image.BICUBIC)
        im = im.filter(ImageFilter.GaussianBlur(1.1))
    return im


def render_policy_page(markdown_path: Path | None = None) -> Image.Image:
    """A page of the (fictional) expenses policy, with real headings, for the layout -> Markdown step."""
    sections = [
        ("Travel and expenses", None),
        ("Submitting expense claims", "Submit expense claims within 30 days. Supplier invoices must show Contoso's VAT "
                                      "number, the supplier's VAT number, the invoice date and the tax amount."),
        ("Meals and per diem", "Meals are reimbursed up to 40 euros per day for domestic trips and 60 euros abroad."),
        ("Mileage", "Business trips in your own car are reimbursed at 0.36 euros per kilometre."),
    ]
    im = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(im)
    y = 110
    for heading, body in sections:
        d.text((90, y), heading, font=_font(56 if body is None else 38), fill="black")
        y += 90 if body is None else 60
        if body:
            words, line = body.split(), ""
            for w in words:
                if d.textlength(f"{line} {w}", font=_font(28)) > WIDTH - 180:
                    d.text((90, y), line.strip(), font=_font(28), fill="black")
                    y, line = y + 40, ""
                line += f" {w}"
            d.text((90, y), line.strip(), font=_font(28), fill="black")
            y += 80
    return im


def write_samples(out: str | Path) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for s in SAMPLES:
        p = out / s.file
        render_invoice(s).save(p, optimize=True)
        paths.append(p)
    p = out / "contoso-expenses-policy.png"
    render_policy_page().save(p, optimize=True)
    paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="invoice_intake.samples", description="Render the fictional sample documents.")
    ap.add_argument("--out", default="samples")
    a = ap.parse_args(argv)
    for p in write_samples(a.out):
        print(f"{p}  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
