#!/usr/bin/env python3
"""Which partitions does an incremental refresh policy create on a given day?

Implements the rules in Learn's "Advanced incremental refresh and real-time data with the XMLA endpoint" (partitions section):
the refresh period is the last N periods up to and including today; everything older, back to the start of the store (rolling
window) period, is covered by whole historical periods, the coarsest that fit: years, then quarters, months, days. A quarter or
year only appears once it is complete, which is how day partitions end up merged into a month, months into a quarter and
quarters into a year. Real-time (hybrid) adds a DirectQuery partition after the refresh period.

Learn's worked example (today 2021-02-02, 3 years, refresh 1 day, real time) is a test. What is NOT verified:
  * the exact partition names. Learn shows "2021Q101" (month) and "2021Q10201" (day); both examples are consistent with a
    calendar month number and with a month number inside the quarter. The calendar month is used here: confirm in SSMS.
  * how the service names the refresh partitions and the DirectQuery partition.

    python ir_partitions.py --model ContosoSalesIR.SemanticModel/definition --date 2026-11-21
    python ir_partitions.py --policy year:3,day:10 --date 2021-02-02 --realtime
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

GRAINS = ["day", "month", "quarter", "year"]


@dataclass(frozen=True)
class Policy:
    rolling_granularity: str = "year"
    rolling_periods: int = 3
    incremental_granularity: str = "day"
    incremental_periods: int = 10
    realtime: bool = False

    def problems(self) -> list:
        out = []
        for g in (self.rolling_granularity, self.incremental_granularity):
            if g not in GRAINS:
                out.append(f"unknown granularity '{g}'")
        if out:
            return out
        if self.rolling_periods < 1 or self.incremental_periods < 1:
            out.append("periods must be at least 1")
        if GRAINS.index(self.incremental_granularity) > GRAINS.index(self.rolling_granularity):
            out.append("the refresh period can't be coarser than the store period")
        elif self.incremental_granularity == self.rolling_granularity and self.incremental_periods >= self.rolling_periods:
            out.append("the refresh period must be shorter than the store period")
        return out


def add_months(d: date, n: int) -> date:
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def period_start(d: date, grain: str) -> date:
    if grain == "year":
        return date(d.year, 1, 1)
    if grain == "quarter":
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    if grain == "month":
        return date(d.year, d.month, 1)
    return d


def shift(start: date, grain: str, n: int) -> date:
    """start (aligned to grain) moved by n periods."""
    if grain == "year":
        return date(start.year + n, 1, 1)
    if grain == "quarter":
        return add_months(start, 3 * n)
    if grain == "month":
        return add_months(start, n)
    return start + timedelta(days=n)


def name(start: date, grain: str, month_style: str = "calendar") -> str:
    """month_style 'calendar': 2026Q41101 for 1 Nov (month 11); 'in-quarter': 2026Q40201 (second month of Q4). Learn's two
    examples (2021Q101, 2021Q10201) fit both: which one the service uses is not verified."""
    q = f"{start.year}Q{(start.month - 1) // 3 + 1}"
    mm = start.month if month_style == "calendar" else (start.month - 1) % 3 + 1
    return {"year": f"{start.year}", "quarter": q, "month": f"{q}{mm:02d}", "day": f"{q}{mm:02d}{start.day:02d}"}[grain]


def partitions(policy: Policy, today: date, month_style: str = "calendar") -> list:
    bad = policy.problems()
    if bad:
        raise ValueError("; ".join(bad))
    store_from = shift(period_start(today, policy.rolling_granularity), policy.rolling_granularity, -policy.rolling_periods)
    refresh_from = shift(period_start(today, policy.incremental_granularity), policy.incremental_granularity, -(policy.incremental_periods - 1))
    refresh_to = shift(period_start(today, policy.incremental_granularity), policy.incremental_granularity, 1)
    allowed = GRAINS[: GRAINS.index(policy.rolling_granularity) + 1]
    out, p = [], store_from
    while p < refresh_from:
        for g in reversed(allowed):
            if period_start(p, g) == p and shift(p, g, 1) <= refresh_from:
                out.append({"name": name(p, g, month_style), "kind": "historical", "grain": g, "start": p, "end": shift(p, g, 1)})
                p = shift(p, g, 1)
                break
        else:                                                   # can't happen: day always fits
            raise AssertionError(p)
    q = refresh_from
    while q < refresh_to:
        n = shift(q, policy.incremental_granularity, 1)
        out.append({"name": name(q, policy.incremental_granularity, month_style), "kind": "refresh", "grain": policy.incremental_granularity, "start": q, "end": n})
        q = n
    if policy.realtime:
        out.append({"name": "(DirectQuery)", "kind": "directquery", "grain": "-", "start": refresh_to, "end": None})
    return out


def transition(policy: Policy, before: date, after: date) -> dict:
    a = {p["name"] for p in partitions(policy, before) if p["kind"] != "directquery"}
    b = {p["name"] for p in partitions(policy, after) if p["kind"] != "directquery"}
    return {"added": sorted(b - a), "removed": sorted(a - b)}


def rows_in(part: dict, daily: dict) -> tuple:
    """(order lines, sales amount cents) from sql_mirror's per-day table, for an import partition."""
    if part["end"] is None:
        return (0, 0)
    lines = cents = 0
    d = part["start"]
    while d < part["end"]:
        v = daily.get(d.isoformat())
        if v:
            lines += v[0]
            cents += v[1]
        d += timedelta(days=1)
    return (lines, cents)


# ---------------------------------------------------------------- reading the policy from TMDL
def read_policy(tmdl_text: str) -> Policy | None:
    m = re.search(r"^\trefreshPolicy\s*\n((?:\t\t.*\n?|\n)+)", tmdl_text, re.M)
    if not m:
        return None
    block = m.group(1)

    def get(key, default):
        k = re.search(rf"^\t\t{key}:\s*(\S+)", block, re.M)
        return k.group(1) if k else default
    return Policy(get("rollingWindowGranularity", "year"), int(get("rollingWindowPeriods", 3)),
                  get("incrementalGranularity", "day"), int(get("incrementalPeriods", 10)),
                  bool(re.search(r"^\t\tmode:\s*hybrid|policyType:\s*hybrid", block, re.M)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", help="SemanticModel/definition folder: reads the policy of its first table that has one")
    ap.add_argument("--policy", help="rolling,refresh as grain:periods, for example year:3,day:10")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD, the day of the refresh")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--month-style", choices=["calendar", "in-quarter"], default="calendar", help="how month numbers in partition names are written (unverified)")
    ap.add_argument("--rows-from", help="expected/daily-*.json from sql_mirror.py: add rows per partition")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pol = None
    if a.model:
        for f in sorted((Path(a.model) / "tables").glob("*.tmdl")):
            pol = read_policy(f.read_text(encoding="utf-8"))
            if pol:
                break
    if a.policy:
        (rg, rp), (ig, ip) = [x.split(":") for x in a.policy.split(",")]
        pol = Policy(rg, int(rp), ig, int(ip))
    if pol is None:
        print("no policy: give --model or --policy", file=sys.stderr)
        return 2
    if a.realtime:
        pol = Policy(**{**pol.__dict__, "realtime": True})
    parts = partitions(pol, date.fromisoformat(a.date), a.month_style)
    daily = json.loads(Path(a.rows_from).read_text())["daily"] if a.rows_from else None
    if a.json:
        print(json.dumps([{**p, "start": p["start"].isoformat(), "end": p["end"].isoformat() if p["end"] else None} for p in parts], indent=1))
        return 0
    print(f"policy: keep {pol.rolling_periods} {pol.rolling_granularity}(s), refresh the last {pol.incremental_periods} {pol.incremental_granularity}(s)"
          + (", real time" if pol.realtime else "") + f"; on {a.date}")
    for p in parts:
        extra = ""
        if daily:
            n, c = rows_in(p, daily)
            extra = f"  {n:>9,} lines"
        print(f"  {p['kind']:<11} {p['name']:<14} {p['start']} .. {p['end'] or 'open'}{extra}")
    print(f"{len(parts)} partition(s): {sum(p['kind'] == 'historical' for p in parts)} historical, {sum(p['kind'] == 'refresh' for p in parts)} refresh"
          + (", 1 DirectQuery" if pol.realtime else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
