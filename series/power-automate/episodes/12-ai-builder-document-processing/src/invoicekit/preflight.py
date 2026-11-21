"""Preflight: does the file meet the limits Learn lists for the prebuilt invoice processing model?

Learn ("Invoice processing prebuilt AI model", Supported languages and files):
  - format JPEG, PNG or PDF
  - file size at most 20 MB
  - image dimensions between 50 x 50 and 10,000 x 10,000 pixels
  - PDF dimensions at most 17 x 17 inches (Legal or A3 or smaller)
  - for PDFs, only the first 2,000 pages are processed
Learn ("Use the invoice processing prebuilt model in Power Automate", Page range): the Pages
parameter takes "1" or "3-5", and the range must contain one invoice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_PDF_INCHES = 17.0
MIN_PX, MAX_PX = 50, 10_000
MAX_PAGES = 2000
PT_PER_INCH = 72.0


@dataclass
class Finding:
    level: str   # error | warning
    code: str
    text: str


def sniff(data: bytes) -> str | None:
    """File type from the first bytes (the extension can lie)."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def check_file(path: str | Path) -> list[Finding]:
    path = Path(path)
    out: list[Finding] = []
    if not path.is_file():
        return [Finding("error", "P00", f"{path.name}: file not found")]
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(16)
    kind = sniff(head)
    if kind is None:
        return [Finding("error", "P01", f"{path.name}: not a PDF, PNG or JPEG (the model reads only those)")]
    if size > MAX_BYTES:
        out.append(Finding("error", "P02", f"{path.name}: {size / 1048576:.1f} MB is over the 20 MB limit"))
    if kind == "pdf":
        out += _check_pdf(path)
    else:
        out += _check_image(path)
    return out


def _check_pdf(path: Path) -> list[Finding]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        pages = list(reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:  # encrypted, truncated, ...
        return [Finding("error", "P03", f"{path.name}: the PDF can't be read ({exc})")]
    out: list[Finding] = []
    if reader.is_encrypted:
        out.append(Finding("error", "P03", f"{path.name}: the PDF is encrypted"))
        return out
    if len(pages) > MAX_PAGES:
        out.append(Finding("warning", "P04", f"{path.name}: {len(pages)} pages, only the first {MAX_PAGES} are processed"))
    for n, page in enumerate(pages[:50], 1):   # the first 50 pages are enough to catch a wrong paper size
        w, h = float(page.mediabox.width) / PT_PER_INCH, float(page.mediabox.height) / PT_PER_INCH
        if max(w, h) > MAX_PDF_INCHES:
            out.append(Finding("error", "P05", f"{path.name} page {n}: {w:.1f} x {h:.1f} inches is over 17 x 17"))
            break
    return out


def _check_image(path: Path) -> list[Finding]:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as im:
            w, h = im.size
    except (UnidentifiedImageError, OSError) as exc:
        return [Finding("error", "P03", f"{path.name}: the image can't be read ({exc})")]
    out = []
    if min(w, h) < MIN_PX:
        out.append(Finding("error", "P06", f"{path.name}: {w} x {h} px is under the 50 x 50 minimum"))
    if max(w, h) > MAX_PX:
        out.append(Finding("error", "P06", f"{path.name}: {w} x {h} px is over the 10,000 x 10,000 maximum"))
    return out


# --- one invoice per Pages range -------------------------------------------------------------------

_START = re.compile(r"invoice\s*(?:no\.?|number|#|id)\s*[:.]?\s*([A-Za-z0-9][A-Za-z0-9\-/]*)", re.I)


def split_invoices(path: str | Path) -> list[tuple[str, str]]:
    """[(invoice id, Pages value)] for a PDF that holds several invoices.

    A page starts a new invoice when the word INVOICE is in its first lines and an invoice number follows a
    label; every other page continues the invoice before it. The Pages value is what you would type into
    the action: "1" or "2-3" (Learn: the range must hold exactly one invoice).
    Pages without a text layer (a scan) can't be read here: those return an empty id.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    starts: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "")
        top = "\n".join(text.splitlines()[:6])
        m = _START.search(text)
        if m and re.search(r"\binvoice\b", top, re.I) and not re.search(r"continued|page\s+[2-9]\s+of", top, re.I):
            starts.append((i, m.group(1)))
    if not starts:
        return []
    ranges = []
    total = len(reader.pages)
    for k, (first, inv_id) in enumerate(starts):
        last = (starts[k + 1][0] - 1) if k + 1 < len(starts) else total
        ranges.append((inv_id, str(first) if first == last else f"{first}-{last}"))
    return ranges
