"""Write fictional test invoices as small text PDFs (no dependencies), for the demo upload.

    python samples/make_samples.py            # -> samples/out/*.pdf

Three cases, one per routing outcome we want to show on camera:
  fabrikam-clean.pdf      totals add up, under the approval limit           -> Ready
  fabrikam-over-limit.pdf 24,600.00 EUR, above the 10,000 approval limit   -> Needs review
  fabrikam-mismatch.pdf   subtotal + tax != total (transposed digits)      -> Needs review
All names, numbers and addresses are fictional.
"""
from __future__ import annotations

import sys
from pathlib import Path

CASES = {
    "fabrikam-clean": dict(number="INV-2026-0417", sub="1,200.00", tax="276.00", total="1,476.00"),
    "fabrikam-over-limit": dict(number="INV-2026-0418", sub="20,000.00", tax="4,600.00", total="24,600.00"),
    "fabrikam-mismatch": dict(number="INV-2026-0419", sub="1,200.00", tax="267.00", total="1,476.00"),
}


def invoice_lines(number: str, sub: str, tax: str, total: str) -> list[tuple[int, int, int, str]]:
    """(x, y, font size, text) in PDF points, A4 portrait."""
    return [
        (56, 780, 20, "Fabrikam Office Supplies"),
        (56, 760, 10, "12 Example Street, 1000-001 Lisboa, Portugal"),
        (380, 780, 20, "INVOICE"),
        (380, 755, 10, f"Invoice number: {number}"),
        (380, 740, 10, "Invoice date: 2026-10-31"),
        (380, 725, 10, "Due date: 2026-11-30"),
        (56, 690, 11, "Bill to: Contoso Ltd"),
        (56, 675, 10, "Purchase order: PO-7781"),
        (56, 630, 11, "Description"), (330, 630, 11, "Qty"), (390, 630, 11, "Unit price"), (480, 630, 11, "Amount"),
        (56, 612, 10, "A4 paper, 80 g, box of 5 reams"), (330, 612, 10, "40"), (390, 612, 10, "30.00 EUR"),
        (480, 612, 10, "1,200.00"),
        (380, 560, 11, f"Subtotal:      {sub} EUR"),
        (380, 544, 11, f"VAT 23%:       {tax} EUR"),
        (380, 524, 13, f"Total due:     {total} EUR"),
        (56, 480, 9, "Fictional document generated for a demo. Not a real invoice."),
    ]


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines) -> bytes:
    """Minimal single-page PDF 1.4 with Helvetica text. Byte offsets in the xref are exact."""
    stream = "\n".join(f"BT /F1 {size} Tf {x} {y} Td ({_esc(text)}) Tj ET" for x, y, size, text in lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def main(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, case in CASES.items():
        p = out_dir / f"{name}.pdf"
        p.write_bytes(build_pdf(invoice_lines(**case)))
        written.append(p)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out"
    for p in main(target):
        print(p, p.stat().st_size, "bytes")
