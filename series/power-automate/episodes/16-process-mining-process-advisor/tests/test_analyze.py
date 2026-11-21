from datetime import datetime, timedelta, timezone

import pytest

from pmkit import analyze, read_csv
from pmkit.analyze import precedence_violations
from pmkit.eventlog import Event

from conftest import CLEAN

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)


def ev(case, activity, hours, minutes=10):
    start = T0 + timedelta(hours=hours)
    return Event(case, activity, start, start + timedelta(minutes=minutes))


def test_the_numbers_for_the_sample_log():
    r = analyze(read_csv(CLEAN))
    assert (r["cases"], r["events"], r["activities"], r["variants"], r["resources"]) == (300, 1781, 9, 17, 6)
    assert (r["avg_case_duration_h"], r["median_case_duration_h"]) == (227.2, 234.1)
    assert (r["self_loop_cases_pct"], r["loop_cases_pct"], r["rework_cases_pct"]) == (7.7, 22.3, 28.0)
    assert [v["count"] for v in r["top_variants"]] == [122, 70, 31, 19, 14]
    assert r["top_variants"][0]["path"] == ["Submit request", "Manager review", "Place order", "Receive goods", "Close request"]
    assert r["activity_stats"]["Manager review"] == {"total_count": 369, "case_count": 300, "max_in_case": 3, "mean_duration_min": 19.3}
    assert r["activity_stats"]["Finance review"]["case_count"] == 106


def test_variant_counts_add_up_to_the_cases():
    r = analyze(read_csv(CLEAN), top=100)
    assert sum(v["count"] for v in r["top_variants"]) == r["cases"] == 300


def test_the_finance_queue_is_the_longest_wait_inside_our_own_process():
    r = analyze(read_csv(CLEAN))
    names = [t["name"] for t in r["slowest_transitions"]]
    assert names[0] == "Place order > Receive goods"  # the supplier's delivery, outside our process
    assert "Manager review > Finance review" in names
    assert r["transitions"]["Manager review > Finance review"]["mean_wait_h"] == 64.7


def test_self_loop_loop_and_no_rework_follow_learns_definitions():
    events = [ev("c1", "A", 0), ev("c1", "A", 1), ev("c1", "B", 2),            # self-loop (A directly after A)
              ev("c2", "A", 0), ev("c2", "B", 1), ev("c2", "A", 2),            # loop (A comes back after B)
              ev("c3", "A", 0), ev("c3", "B", 1), ev("c3", "C", 2),            # none
              ev("c4", "A", 0), ev("c4", "A", 1), ev("c4", "B", 2), ev("c4", "A", 3)]  # both
    r = analyze(events)
    assert r["cases"] == 4
    assert r["self_loop_cases_pct"] == 50.0 and r["loop_cases_pct"] == 50.0 and r["rework_cases_pct"] == 75.0


def test_transition_wait_is_next_start_minus_previous_end():
    r = analyze([ev("c1", "A", 0, minutes=30), ev("c1", "B", 3)], min_cases=1)
    t = r["transitions"]["A > B"]
    assert t == {"count": 1, "mean_wait_h": 2.5, "total_wait_h": 2.5}


def test_case_duration_runs_from_the_first_start_to_the_last_end():
    r = analyze([ev("c1", "A", 0), ev("c1", "B", 10, minutes=60), ev("c2", "A", 0), ev("c2", "B", 2, minutes=60)])
    assert r["avg_case_duration_h"] == 7.0 and r["median_case_duration_h"] == 7.0  # (11 h + 3 h) / 2


def test_events_with_the_same_start_keep_file_order():
    a, b = ev("c1", "First", 1), ev("c1", "Second", 1)
    assert analyze([a, b])["top_variants"][0]["path"] == ["First", "Second"]
    assert analyze([b, a])["top_variants"][0]["path"] == ["Second", "First"]


def test_precedence_violations_find_orders_placed_before_approval():
    events = read_csv(CLEAN)
    bad = precedence_violations(events, "Manager review", "Place order")
    assert len(bad) == 8 and bad[:3] == ["PR-0021", "PR-0036", "PR-0108"]
    # the same cases show up as a variant of their own
    r = analyze(events, top=100)
    variant = ["Submit request", "Place order", "Manager review", "Receive goods", "Close request"]
    assert any(v["path"] == variant for v in r["top_variants"])


def test_precedence_when_the_first_activity_never_happens():
    assert precedence_violations([ev("c1", "Place order", 0)], "Manager review", "Place order") == ["c1"]
