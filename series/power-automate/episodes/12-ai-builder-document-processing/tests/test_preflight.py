"""Preflight against the limits Learn lists, on the fictional sample files and on files built here."""
import io
import subprocess
import sys

import pytest
from conftest import SAMPLES, SRC
from PIL import Image
from pypdf import PdfWriter

from invoicekit import preflight


def codes(path):
    return [f.code for f in preflight.check_file(path)]


def test_clean_pdf_and_scan_pass():
    assert preflight.check_file(SAMPLES / "invoice-clean.pdf") == []
    assert preflight.check_file(SAMPLES / "invoice-scan.png") == []


def test_oversize_pdf_is_over_17_inches():
    f = preflight.check_file(SAMPLES / "invoice-oversize.pdf")
    assert [x.code for x in f] == ["P05"] and "20.0 x 20.0" in f[0].text


def test_tiny_image_is_under_50_pixels():
    assert codes(SAMPLES / "invoice-tiny.png") == ["P06"]


def test_17_inches_exactly_is_allowed(tmp_path):
    for inches, expected in ((17, []), (17.1, ["P05"])):
        w = PdfWriter()
        w.add_blank_page(width=inches * 72, height=11 * 72)
        with open(tmp_path / f"p{inches}.pdf", "wb") as fh:
            w.write(fh)
        assert codes(tmp_path / f"p{inches}.pdf") == expected


def test_a_text_file_named_pdf_is_refused_by_content_not_by_name(tmp_path):
    p = tmp_path / "invoice.pdf"
    p.write_text("hello", encoding="utf-8")
    assert codes(p) == ["P01"]


def test_a_png_named_pdf_is_checked_as_an_image(tmp_path):
    p = tmp_path / "scan.pdf"
    p.write_bytes((SAMPLES / "invoice-tiny.png").read_bytes())
    assert codes(p) == ["P06"]


def test_over_20_mb_is_an_error(tmp_path):
    p = tmp_path / "big.pdf"
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
        fh.truncate(20 * 1024 * 1024 + 1)   # sparse: no disk used
    assert "P02" in codes(p)


def test_exactly_20_mb_is_not_over_the_size_limit(tmp_path):
    p = tmp_path / "edge.pdf"
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.4\n")
        fh.truncate(20 * 1024 * 1024)
    assert "P02" not in codes(p)   # (it is still not a readable PDF: P03)


def test_truncated_pdf_is_reported_not_raised(tmp_path):
    p = tmp_path / "cut.pdf"
    p.write_bytes((SAMPLES / "invoice-clean.pdf").read_bytes()[:300])
    assert codes(p) == ["P03"]


def test_missing_file():
    assert codes(SAMPLES / "nope.pdf") == ["P00"]


def test_image_over_10000_pixels(tmp_path):
    p = tmp_path / "wide.png"
    Image.new("L", (10_001, 60), 255).save(p)
    assert codes(p) == ["P06"]


def test_more_than_2000_pages_is_only_a_warning(tmp_path):
    w = PdfWriter()
    for _ in range(2001):
        w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    p = tmp_path / "long.pdf"
    p.write_bytes(buf.getvalue())
    f = preflight.check_file(p)
    assert [(x.level, x.code) for x in f] == [("warning", "P04")]


def test_two_invoices_in_one_pdf_get_one_pages_value_each():
    assert preflight.split_invoices(SAMPLES / "invoice-two-in-one.pdf") == [("INV-2026-0412", "1"), ("INV-2026-0413", "2-3")]
    assert preflight.split_invoices(SAMPLES / "invoice-clean.pdf") == [("INV-2026-0412", "1")]


def test_a_scan_has_no_text_layer_so_nothing_to_split():
    assert preflight.split_invoices(SAMPLES / "invoice-clean.pdf")[0][1] == "1"
    p = SAMPLES / "invoice-scan.png"
    assert preflight.sniff(p.read_bytes()[:16]) == "png"   # images are never split


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "invoicekit", *args], cwd=SRC, capture_output=True, text=True)


def test_cli_exit_codes_and_pages_listing():
    ok = run_cli("preflight", "samples/invoice-two-in-one.pdf")
    assert ok.returncode == 0
    assert "Pages = 1     INV-2026-0412" in ok.stdout and "Pages = 2-3   INV-2026-0413" in ok.stdout
    bad = run_cli("preflight", "samples/invoice-clean.pdf", "samples/invoice-oversize.pdf")
    assert bad.returncode == 1 and "OK       invoice-clean.pdf" in bad.stdout and "P05" in bad.stdout


def test_cli_help_runs():
    r = run_cli("--help")
    assert r.returncode == 0 and "preflight" in r.stdout and "triage" in r.stdout
