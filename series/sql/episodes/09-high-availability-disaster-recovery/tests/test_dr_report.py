"""dr_report.assess: one test per rule."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import dr_report as dr  # noqa: E402

T = datetime(2026, 11, 21, 10, 0)


def row(name="Db", model="FULL", state="ONLINE", standby=0, full=T, diff=None, log=T, minutes=5):
    return (name, model, state, standby, full, diff, log, minutes)


def one(r, rpo=15):
    return dr.assess([r], rpo)[0]


def test_recent_backup_is_ok():
    v = one(row(minutes=5))
    assert v.verdict == dr.OK and "5 min" in v.reason and "target 15" in v.reason


def test_exactly_at_the_target_is_ok_and_one_minute_more_is_at_risk():
    assert one(row(minutes=15)).verdict == dr.OK
    assert one(row(minutes=16)).verdict == dr.AT_RISK


def test_no_backup_at_all():
    v = one(row(full=None, log=None, minutes=None))
    assert v.verdict == dr.NO_BACKUP and "no full backup" in v.reason


def test_log_backup_without_a_full_backup_is_still_no_backup():
    v = one(row(full=None, log=T, minutes=3))
    assert v.verdict == dr.NO_BACKUP and "cannot be restored" in v.reason


def test_restoring_database_is_skipped():
    v = one(row(state="RESTORING", minutes=1))
    assert v.verdict == dr.SKIPPED and "RESTORING" in v.reason


def test_read_only_standby_is_skipped_even_without_backups():
    v = one(row(standby=1, full=None, log=None, minutes=None))
    assert v.verdict == dr.SKIPPED and "standby" in v.reason


def test_simple_recovery_reason_mentions_no_log_backups():
    v = one(row(model="SIMPLE", log=None, minutes=7))
    assert v.verdict == dr.OK and "SIMPLE recovery" in v.reason


def test_full_recovery_without_log_backup_is_flagged_in_the_reason():
    v = one(row(log=None, minutes=7))
    assert v.verdict == dr.OK and "no log backup yet" in v.reason


def test_at_risk_keeps_the_notes():
    v = one(row(model="SIMPLE", log=None, minutes=600))
    assert v.verdict == dr.AT_RISK and "600 min" in v.reason and "SIMPLE" in v.reason


def test_order_is_kept_and_render_lines_up():
    rows = [row("A", minutes=1), row("Bb", state="RESTORING"), row("C", full=None, log=None, minutes=None)]
    out = dr.assess(rows, 15)
    assert [v.name for v in out] == ["A", "Bb", "C"] and [v.verdict for v in out] == [dr.OK, dr.SKIPPED, dr.NO_BACKUP]
    lines = dr.render(out).splitlines()
    assert len(lines) == 3 and lines[0].startswith("A ")
    assert dr.render([]) == "(no user databases)"


def test_negative_target_is_rejected():
    with pytest.raises(ValueError):
        dr.assess([row()], -1)


def test_accepts_exposure_objects():
    e = dr.Exposure.from_row(row(minutes=2))
    assert dr.assess([e], 15)[0].verdict == dr.OK
