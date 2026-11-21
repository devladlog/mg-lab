import json
from datetime import date

import pytest

import ir_partitions as ip
from conftest import DAILY, MODEL

LEARN = ip.Policy("year", 3, "day", 1, realtime=True)       # Learn's example: 3 years, 1 day, real time, today 2021-02-02


def names(parts, kind=None):
    return [p["name"] for p in parts if kind is None or p["kind"] == kind]


def test_learns_worked_example_2021_02_02():
    parts = ip.partitions(LEARN, date(2021, 2, 2))
    # DirectQuery + today + yesterday (day) + January (month) + 2020, 2019, 2018 (years); no quarter yet
    assert [(p["kind"], p["grain"]) for p in parts] == [("historical", "year")] * 3 + [("historical", "month"), ("historical", "day"), ("refresh", "day"), ("directquery", "-")]
    assert names(parts, "historical")[:3] == ["2018", "2019", "2020"]
    assert names(parts, "historical")[3:] == ["2021Q101", "2021Q10201"]                  # the two names Learn prints
    assert parts[-1]["start"] == date(2021, 2, 3) and parts[-2]["start"] == date(2021, 2, 2)


def test_in_quarter_naming_gives_the_same_names_for_learns_months():
    parts = ip.partitions(LEARN, date(2021, 2, 2), "in-quarter")
    assert names(parts, "historical")[3:] == ["2021Q101", "2021Q10201"]
    nov = ip.partitions(ip.Policy(), date(2026, 11, 21), "in-quarter")
    cal = ip.partitions(ip.Policy(), date(2026, 11, 21), "calendar")
    assert names(nov)[-1] == "2026Q40221" and names(cal)[-1] == "2026Q41121"             # they only differ from the second month of a quarter on


def test_one_day_policy_merges_as_periods_close():
    p = ip.Policy("year", 3, "day", 1)
    # first day of a month: the day partitions of the previous month become a month partition
    assert "2021Q10228" in names(ip.partitions(p, date(2021, 2, 28)))
    t = ip.transition(p, date(2021, 2, 28), date(2021, 3, 1))
    assert "2021Q102" in t["added"] and "2021Q10201" in t["removed"] and "2021Q10227" in t["removed"]
    # first day of a quarter: three months become a quarter
    assert "2021Q1" in names(ip.partitions(p, date(2021, 4, 1))) and "2021Q101" not in names(ip.partitions(p, date(2021, 4, 1)))
    # first day of a year: four quarters become a year
    after = names(ip.partitions(p, date(2022, 1, 1)))
    assert "2021" in after and "2021Q1" not in after


def test_the_oldest_year_is_kept_until_the_first_refresh_of_the_next_year():
    p = ip.Policy("year", 3, "day", 1)
    assert "2018" in names(ip.partitions(p, date(2021, 12, 31)))
    assert "2018" not in names(ip.partitions(p, date(2022, 1, 1)))           # Learn: retained until the first refresh on January 1, 2022


def test_lab_policy_on_the_recording_day():
    parts = ip.partitions(ip.Policy("year", 3, "day", 10), date(2026, 11, 21))
    assert len(parts) == 28
    assert names(parts, "historical")[:7] == ["2023", "2024", "2025", "2026Q1", "2026Q2", "2026Q3", "2026Q410"]
    assert sum(p["kind"] == "refresh" for p in parts) == 10
    assert parts[-10]["start"] == date(2026, 11, 12) and parts[-1]["end"] == date(2026, 11, 22)


def test_partitions_are_contiguous_and_cover_the_window_exactly():
    for today in (date(2026, 11, 21), date(2026, 1, 1), date(2026, 3, 31), date(2024, 2, 29), date(2025, 12, 31)):
        for pol in (ip.Policy(), ip.Policy("year", 3, "day", 1), ip.Policy("quarter", 8, "month", 2), ip.Policy("month", 12, "day", 7), ip.Policy("year", 5, "month", 3)):
            parts = [p for p in ip.partitions(pol, today) if p["end"]]
            for a, b in zip(parts, parts[1:]):
                assert a["end"] == b["start"], (today, pol)
            first = ip.shift(ip.period_start(today, pol.rolling_granularity), pol.rolling_granularity, -pol.rolling_periods)
            assert parts[0]["start"] == first
            assert parts[-1]["end"] == ip.shift(ip.period_start(today, pol.incremental_granularity), pol.incremental_granularity, 1)


def test_refresh_period_crossing_a_month_boundary_keeps_days_not_a_month():
    parts = ip.partitions(ip.Policy("year", 3, "day", 10), date(2026, 2, 5))
    hist = [p for p in parts if p["kind"] == "historical" and p["start"].year == 2026]
    assert [p["grain"] for p in hist] == ["day"] * 26 and hist[0]["start"] == date(2026, 1, 1)       # Jan 1..26 as days, Jan 27 .. Feb 5 refresh


def test_monthly_refresh_period():
    parts = ip.partitions(ip.Policy("year", 2, "month", 2), date(2026, 11, 21))
    assert names([p for p in parts if p["kind"] == "refresh"]) == ["2026Q410", "2026Q411"]
    assert all(p["grain"] != "day" for p in parts)


@pytest.mark.parametrize("pol,why", [
    (ip.Policy("year", 1, "year", 1), "shorter"), (ip.Policy("month", 3, "year", 1), "coarser"),
    (ip.Policy("year", 0, "day", 1), "at least 1"), (ip.Policy("decade", 1, "day", 1), "unknown"),
])
def test_invalid_policies(pol, why):
    assert any(why in p for p in pol.problems())
    with pytest.raises(ValueError):
        ip.partitions(pol, date(2026, 1, 1))


def test_policy_is_read_from_the_tmdl_and_the_lab_policy_matches():
    pol = ip.read_policy((MODEL / "tables" / "Sales.tmdl").read_text(encoding="utf-8"))
    assert pol == ip.Policy("year", 3, "day", 10)
    assert ip.read_policy("table X\n") is None


def test_rows_per_partition_add_up_to_what_a_refresh_on_that_day_loads():
    daily = json.loads(DAILY.read_text(encoding="utf-8"))["daily"]
    parts = ip.partitions(ip.Policy(), date(2026, 11, 21))
    total = sum(ip.rows_in(p, daily)[0] for p in parts)
    assert total == sum(v[0] for d, v in daily.items() if d < "2026-11-22")
    assert ip.rows_in(parts[0], daily)[0] == 499_655                       # partition 2023
    assert ip.rows_in({"start": date(2026, 12, 1), "end": None}, daily) == (0, 0)


def test_cli(capsys):
    assert ip.main(["--model", str(MODEL), "--date", "2026-11-21", "--rows-from", str(DAILY)]) == 0
    out = capsys.readouterr().out
    assert "28 partition(s): 18 historical, 10 refresh" in out and "2023" in out and "499,655 lines" in out
    assert ip.main(["--policy", "year:3,day:1", "--date", "2021-02-02", "--realtime"]) == 0
    assert "1 DirectQuery" in capsys.readouterr().out
    assert ip.main(["--date", "2026-11-21"]) == 2
