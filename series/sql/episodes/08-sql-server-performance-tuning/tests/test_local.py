"""The local half: the lab's data, workload statements, rollback and the wait-delta query on DuckDB, and expected/
checked against independent readings of the scripts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import perf_lab as lab  # noqa: E402


def expected(key):
    return labdb.read_csv(ROOT / "expected" / f"{key}.csv")


def test_local_run_matches_expected(capsys):
    assert lab.run_local() == 0
    out = capsys.readouterr().out
    assert "200000 orders loaded" in out and "wait-delta query behave as expected" in out


def test_delta_query_is_extracted_between_the_markers():
    q = lab.extract_delta_query()
    assert q.startswith("SELECT TOP (@Top)") and "FROM Tune.WaitSnapshot" in q and "delta-query" not in q
    assert not q.endswith(";")


def delta(snap_a, snap_b, top=10):
    eng = labdb.DuckDBEngine(schemas=("Tune",))
    try:
        eng.run_file(lab.SQL_DIR / "10-tune-tools.sql")
        for label, snap in (("a", snap_a), ("b", snap_b)):
            for w in snap:
                eng.con.execute("INSERT INTO Tune.WaitSnapshot VALUES (?, ?, ?, ?, ?)", [label, *w])
        columns, rows = eng.query(lab.delta_sql())
        return labdb.to_table(columns, rows[:top])[1:]
    finally:
        eng.close()


def test_a_wait_that_did_not_change_is_not_listed():
    rows = delta([("WRITELOG", 5, 100, 1)], [("WRITELOG", 5, 100, 1)])
    assert rows == []


def test_a_wait_that_first_appears_in_the_second_snapshot_counts_in_full():
    rows = delta([("WRITELOG", 5, 100, 1)], [("WRITELOG", 5, 100, 1), ("LCK_M_X", 2, 700, 3)])
    assert rows == [["LCK_M_X", "2", "700", "3"]]


def test_background_waits_are_not_on_the_watch_list():
    rows = delta([], [("SLEEP_TASK", 9, 99999, 0), ("LAZYWRITER_SLEEP", 9, 99999, 0), ("PAGELATCH_EX", 1, 5, 0)])
    assert [r[0] for r in rows] == ["PAGELATCH_EX"]


def test_every_watch_list_family_is_listed_once_and_sorted_by_time():
    waits = [(w, 1, i * 10, 0) for i, w in enumerate(
        ["LCK_M_U", "PAGEIOLATCH_EX", "PAGELATCH_SH", "WRITELOG", "SOS_SCHEDULER_YIELD", "CXPACKET", "CXCONSUMER",
         "ASYNC_NETWORK_IO", "RESOURCE_SEMAPHORE", "THREADPOOL"], start=1)]
    rows = delta([], waits)
    assert [r[0] for r in rows] == [w[0] for w in reversed(waits)]


def test_top_limits_the_rows():
    waits = [("LCK_M_S", 1, 10, 0), ("WRITELOG", 1, 20, 0), ("CXPACKET", 1, 30, 0)]
    assert [r[0] for r in delta([], waits, top=2)] == ["CXPACKET", "WRITELOG"]


def test_wildcard_diff():
    assert lab.diff_wild([["a", "b"], ["x", "*"]], [["a", "b"], ["x", "7"]]) == []
    assert lab.diff_wild([["a", "b"], ["x", "*"]], [["a", "b"], ["y", "7"]])
    assert lab.diff_wild([["a"], ["*"]], [["a"], ["1"], ["2"]])


def test_workload_counts_in_expected_match_the_loops_in_w01():
    text = lab.sql_text("w01-workload")
    loops = [int(n) for n in re.findall(r"WHILE @(?:i|id) <= (\d+)", text)]
    rows = {r[0]: r for r in expected("t02-top-queries")[1:]}
    assert loops == [int(rows["scan"][1]), int(rows["seek"][1])] == [3, 50]
    assert rows["scan"][2] == "1" and rows["seek"][2] == "2"


def test_workload_statements_have_markers_and_no_assignment_after_stripping():
    work = lab.workload_statements()
    assert set(work) == {"scan", "seek"}
    assert work["scan"].startswith("SELECT COUNT(*)") and work["seek"].startswith("SELECT Status")


def test_expected_blocking_story_is_consistent():
    rows = {r[0]: r[1] for r in expected("t03-blocking")[1:]}
    assert rows["Wait type of the blocked reader"] == "LCK_M_S"
    assert rows["Reader result after the rollback"] == rows["RCSI reader result while the writer is still open"] == "Shipped"
    # the reader's committed value is the seed's value for order 1 (the blocker only changes it to Cancelled)
    seed = lab.sql_text("01-schema-and-data.sql")
    assert "WHEN s.value % 100 = 7 THEN 'Open'" in seed and "'Shipped'" in seed
    assert expected("t04-wait-delta")[1] == ["Top watch-list wait without RCSI", "LCK_M_S"]


def test_t01_expected_defaults_are_the_ones_in_the_script():
    text = lab.sql_text("t01-config-review")
    for item, default in {r[0]: r[2] for r in expected("t01-config-review")[1:4]}.items():
        assert item in text and default in text
