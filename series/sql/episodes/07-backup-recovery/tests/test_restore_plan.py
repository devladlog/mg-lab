"""restore_plan.py: which backups does a point-in-time restore need? Synthetic msdb rows, one test per rule
(Learn's restore sequence, differential base, copy-only, log chain gaps, target after the last log)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import restore_plan as rp  # noqa: E402

T0 = datetime(2026, 11, 21, 9, 0, 0)


def row(kind, minute, first, last, name, copy_only=False, length=1):
    start = T0 + timedelta(minutes=minute)
    return rp.BackupRow(kind, start, start + timedelta(minutes=length), Decimal(first), Decimal(last), copy_only, name)


def lab_history():
    """Full, differential, log 1, then (after the incident) log 2: the lab's own history."""
    return [row("D", 0, 100, 200, "full.bak"), row("I", 10, 100, 300, "diff.bak"),
            row("L", 20, 200, 400, "log1.trn"), row("L", 40, 400, 600, "log2.trn")]


def names(plan):
    return [s.device for s in plan.steps]


def test_lab_history_picks_full_diff_and_both_logs():
    plan = rp.build_plan(lab_history(), T0 + timedelta(minutes=35))
    assert names(plan) == ["full.bak", "diff.bak", "log1.trn", "log2.trn"] and plan.warnings == []


def test_only_the_most_recent_differential_is_restored():
    rows = lab_history() + [row("I", 15, 100, 350, "diff2.bak")]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=35))
    assert names(plan)[:2] == ["full.bak", "diff2.bak"]


def test_a_differential_after_the_target_is_ignored():
    plan = rp.build_plan(lab_history() + [row("I", 50, 100, 700, "diff-late.bak")], T0 + timedelta(minutes=35))
    assert "diff-late.bak" not in names(plan)


def test_target_before_the_differential_restores_full_and_logs_only():
    rows = [row("D", 0, 100, 200, "full.bak"), row("L", 5, 200, 250, "log0.trn"), row("I", 10, 100, 300, "diff.bak")]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=8))
    assert names(plan) == ["full.bak", "log0.trn"]


def test_logs_stop_at_the_first_log_that_reaches_the_target():
    plan = rp.build_plan(lab_history() + [row("L", 60, 600, 800, "log3.trn")], T0 + timedelta(minutes=35))
    assert "log3.trn" not in names(plan) and names(plan)[-1] == "log2.trn"


def test_copy_only_full_is_never_the_base():
    rows = lab_history() + [row("D", 5, 150, 250, "copyonly.bak", copy_only=True)]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=35))
    assert names(plan)[0] == "full.bak"


def test_newer_full_becomes_the_base_and_older_differential_is_not_used():
    rows = lab_history() + [row("D", 30, 700, 750, "full2.bak"), row("L", 32, 750, 850, "log-after-full2.trn")]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=34))
    assert names(plan) == ["full2.bak", "log-after-full2.trn"]


def test_older_full_is_used_when_the_target_is_before_the_newer_full():
    rows = lab_history() + [row("D", 30, 700, 750, "full2.bak")]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=25))
    assert names(plan)[0] == "full.bak"
    assert all(s.device != "full2.bak" for s in plan.steps)


def test_a_differential_of_the_next_full_does_not_belong_to_the_older_full():
    rows = lab_history() + [row("D", 30, 700, 750, "full2.bak"), row("I", 35, 700, 760, "diff-of-full2.bak")]
    plan = rp.build_plan(rows, T0 + timedelta(minutes=25))
    assert "diff-of-full2.bak" not in names(plan)


def test_gap_in_the_log_chain_is_an_error():
    rows = [row("D", 0, 100, 200, "full.bak"), row("L", 20, 250, 400, "log1.trn")]    # 200-250 missing
    with pytest.raises(rp.PlanError, match="log chain broken"):
        rp.build_plan(rows, T0 + timedelta(minutes=30))


def test_gap_between_two_logs_is_an_error():
    rows = [row("D", 0, 100, 200, "full.bak"), row("L", 20, 200, 400, "log1.trn"), row("L", 40, 450, 600, "log2.trn")]
    with pytest.raises(rp.PlanError, match="log2.trn"):
        rp.build_plan(rows, T0 + timedelta(minutes=45))


def test_no_full_backup_before_the_target():
    with pytest.raises(rp.PlanError, match="no full backup"):
        rp.build_plan(lab_history(), T0 - timedelta(minutes=5))


def test_target_after_the_last_log_warns():
    plan = rp.build_plan(lab_history(), T0 + timedelta(minutes=90))
    assert names(plan)[-1] == "log2.trn" and plan.warnings and "RESTORING" in plan.warnings[0]


def test_log_taken_before_the_base_is_skipped():
    rows = [row("L", 1, 10, 100, "old.trn")] + lab_history()
    assert "old.trn" not in names(rp.build_plan(rows, T0 + timedelta(minutes=35)))


def test_render_uses_norecovery_checksum_and_the_same_stopat_everywhere():
    plan = rp.build_plan(lab_history(), T0 + timedelta(minutes=35, seconds=12, milliseconds=340))
    sql = rp.render(plan, "ContosoBikesRecovered", {"ContosoBikesBackup": "C:\\d\\copy.mdf"})
    assert len(sql) == 5 and sql[-1] == "RESTORE DATABASE ContosoBikesRecovered WITH RECOVERY;"
    assert sql[0].startswith("RESTORE DATABASE") and "MOVE N'ContosoBikesBackup' TO N'C:\\d\\copy.mdf'" in sql[0]
    assert sql[2].startswith("RESTORE LOG") and sql[3].startswith("RESTORE LOG")
    stops = {s.split("STOPAT = ")[1].rstrip(";") for s in sql[:-1]}
    assert stops == {"'2026-11-21T09:35:12.340'"}
    assert all("WITH NORECOVERY" in s or ", NORECOVERY," in s for s in sql[:-1]) and all("CHECKSUM" in s for s in sql[:-1])
    assert "MOVE" not in sql[1]                                   # only the first RESTORE moves files


def test_render_doubles_quotes_in_paths():
    t = T0
    plan = rp.Plan([rp.BackupRow("D", t, t, Decimal(1), Decimal(2), False, "C:\\o'brien\\f.bak")], t)
    assert "N'C:\\o''brien\\f.bak'" in rp.render(plan, "X", {})[0]
