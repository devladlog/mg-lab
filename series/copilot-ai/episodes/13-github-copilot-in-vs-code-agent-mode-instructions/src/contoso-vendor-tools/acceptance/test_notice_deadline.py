"""Acceptance check for the live demo task. Run AFTER the agent finishes:

    python -m pytest acceptance -q

The task given to the agent: show the notice deadline (renewal date minus notice_days) for
each vendor in the renewals report, and flag vendors whose deadline has already passed.
These tests fail on the untouched repository and pass for any implementation that does it.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vendor_tools.cli import render  # noqa: E402
from vendor_tools.renewals import load_vendors, notice_deadline  # noqa: E402

DATA = ROOT / "data" / "vendors.csv"


def test_notice_deadline_is_renewal_minus_notice_days():
    fabrikam = load_vendors(DATA)[0]
    assert notice_deadline(fabrikam) == date(2026, 12, 31)


def test_render_shows_notice_by_column():
    text = render(load_vendors(DATA), date(2026, 12, 1), 130)
    assert "Notice by" in text
    assert "2026-12-31" in text


def test_render_flags_passed_notice_deadline():
    text = render(load_vendors(DATA), date(2027, 1, 15), 100)
    fabrikam_line = next(line for line in text.splitlines() if line.startswith("Fabrikam Cloud"))
    assert "NOTICE PASSED" in fabrikam_line
