import csv
from datetime import timedelta

from pmkit import COLUMNS, generate, make_dirty, read_csv, write_csv
from pmkit.generate import THRESHOLD

from conftest import CLEAN, RAW

ACTIVITIES = {"Submit request", "Manager review", "Request more information", "Revise request", "Reject request",
              "Finance review", "Place order", "Receive goods", "Close request"}


def test_generator_is_deterministic():
    a, b = generate(50, seed=1), generate(50, seed=1)
    assert [e.row() for e in a] == [e.row() for e in b]
    assert [e.row() for e in a] != [e.row() for e in generate(50, seed=2)]


def test_committed_samples_are_what_the_generator_writes(tmp_path):
    write_csv(tmp_path / "clean.csv", generate())
    assert (tmp_path / "clean.csv").read_bytes() == CLEAN.read_bytes()
    with open(tmp_path / "raw.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(COLUMNS)
        w.writerows(make_dirty(generate()))
    assert (tmp_path / "raw.csv").read_bytes() == RAW.read_bytes()


def test_the_log_is_internally_consistent():
    events = read_csv(CLEAN)
    assert {e.activity for e in events} == ACTIVITIES
    assert len({e.case_id for e in events}) == 300
    assert all(e.end and e.end >= e.start for e in events)
    by_case = {}
    for e in events:
        by_case.setdefault(e.case_id, []).append(e)
    for evs in by_case.values():
        assert len({(e.amount, e.category) for e in evs}) == 1  # case level attributes don't vary inside a case
        starts = [e.start for e in evs]
        assert starts == sorted(starts)


def test_events_start_in_working_hours():
    events = read_csv(CLEAN)
    # the generator moves every start into Monday-Friday 08:00-17:59 UTC
    assert all(e.start.weekday() < 5 and 8 <= e.start.hour < 18 for e in events)


def test_finance_review_happens_only_above_the_threshold():
    by_case = {}
    for e in read_csv(CLEAN):
        by_case.setdefault(e.case_id, []).append(e)
    for evs in by_case.values():
        names = [e.activity for e in evs]
        if "Finance review" in names:
            assert evs[0].amount >= THRESHOLD
        elif "Close request" in names:
            assert evs[0].amount < THRESHOLD


def test_timestamps_are_iso_8601_with_a_space_and_no_offset():
    text = CLEAN.read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(COLUMNS)
    first = text.splitlines()[1].split(",")
    assert len(first[2]) == 19 and first[2][10] == " " and first[2][:4] == "2026"
    assert "+" not in text.splitlines()[1] and "Z" not in text.splitlines()[1]


def test_csv_is_utf8_comma_separated_without_a_bom():
    raw = CLEAN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    assert CLEAN.stat().st_size < 1_000_000  # far below the 100 MB the trial allows per process


def test_the_log_is_history_not_the_future():
    from datetime import datetime, timezone
    events = read_csv(CLEAN)
    assert max(e.end for e in events) < datetime(2026, 11, 21, tzinfo=timezone.utc)
