import csv

import pytest

from pmkit import check, clean, generate, write_csv
from pmkit.validate import parse_any

from conftest import CLEAN, RAW


def codes(path, **kw):
    return {f.code for f in check(path, **kw)}


def write(tmp_path, header, rows, name="log.csv"):
    p = tmp_path / name
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return p


H = ["CaseId", "ActivityName", "StartTimestamp", "EndTimestamp"]


def test_the_clean_sample_has_no_findings():
    assert check(CLEAN) == []


def test_the_raw_sample_trips_every_data_rule_we_planted():
    found = {f.code for f in check(RAW)}
    assert {"PM002", "PM003", "PM004", "PM005", "PM006", "PM009"} <= found
    assert any(f.level == "error" for f in check(RAW))


def test_missing_mandatory_column(tmp_path):
    p = write(tmp_path, ["CaseId", "StartTimestamp"], [["A", "2026-01-01 08:00:00"]])
    (f,) = check(p)
    assert f.code == "PM001" and "ActivityName" in f.message


def test_empty_mandatory_values_and_iso_check(tmp_path):
    p = write(tmp_path, H, [["", "A", "2026-01-01 08:00:00", ""], ["C1", "", "2026-01-01 08:00:00", ""],
                            ["C1", "B", "01/02/2026 10:00", ""], ["C2", "A", "", ""]])
    assert {"PM002", "PM003"} <= codes(p)
    assert [f.message for f in check(p) if f.code == "PM002"] == [
        "1 row(s) have an empty CaseId", "1 row(s) have an empty ActivityName", "1 row(s) have an empty StartTimestamp"]


def test_single_event_cases_and_ids_in_activity_names(tmp_path):
    p = write(tmp_path, H, [["A", "Order 123456", "2026-01-01 08:00:00", ""], ["B", "Close", "2026-01-01 08:00:00", ""],
                            ["B", "Open", "2026-01-01 09:00:00", ""]])
    assert {"PM007", "PM008"} <= codes(p)


def test_file_bigger_than_the_trial_capacity(tmp_path):
    assert "PM010" in codes(CLEAN, max_mb=0.1)
    assert "PM010" not in codes(CLEAN)


def test_clean_repairs_the_raw_log_back_to_the_original_bytes(tmp_path):
    events, report = clean(RAW)
    write_csv(tmp_path / "fixed.csv", events)
    assert (tmp_path / "fixed.csv").read_bytes() == CLEAN.read_bytes()
    assert check(tmp_path / "fixed.csv") == []
    # what we planted in make_dirty: 3 rows without a case id, 12 duplicates, 8 swapped, 14 + 10 odd timestamps
    assert report == {"dropped_incomplete_rows": 3, "dropped_duplicates": 12, "swapped_start_end": 8,
                      "converted_timestamps": 24, "renamed_activities": 18}


def test_clean_keeps_the_most_common_spelling(tmp_path):
    p = write(tmp_path, H, [["A", "Manager review", "2026-01-01 08:00:00", ""], ["B", "Manager review", "2026-01-01 08:00:00", ""],
                            ["C", "manager review ", "2026-01-01 08:00:00", ""]])
    events, report = clean(p)
    assert {e.activity for e in events} == {"Manager review"} and report == {"renamed_activities": 1}


def test_day_first_is_the_default_and_month_first_is_an_option():
    assert parse_any("03/04/2026 10:30").month == 4
    assert parse_any("03/04/2026 10:30", day_first=False).month == 3
    assert parse_any("2026-04-03T10:30:00+01:00").hour == 9  # converted to UTC


def test_clean_drops_rows_it_cannot_read(tmp_path):
    p = write(tmp_path, H, [["A", "X", "yesterday", ""], ["A", "X", "2026-01-01 08:00:00", ""]])
    events, report = clean(p)
    assert len(events) == 1 and report == {"dropped_unreadable_timestamps": 1}
