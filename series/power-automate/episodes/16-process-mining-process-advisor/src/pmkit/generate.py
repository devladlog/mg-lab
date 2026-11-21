"""A fictional purchasing event log for the purchasing scenario of episodes 2, 3, 4 and 13 (Contoso, Alex Demo ...).

Deterministic: the same seed gives the same file. Only `random.random()` and arithmetic are used, so the numbers don't
depend on the Python version. Nothing here is real data.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .eventlog import Event, fmt

REQUESTERS = ["Alex Demo", "Riley Demo", "Taylor Demo"]
MANAGER, FINANCE, BUYER, ROBOT = "Sam Demo", "Jordan Demo", "Taylor Demo", "Power Automate"
CATEGORIES = {"IT equipment": (800, 18000), "Office furniture": (200, 4000), "Software": (100, 9000),
              "Services": (500, 25000)}
THRESHOLD = 5000  # same finance threshold as the purchasing episodes
START = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
CASES = 300


def working(ts: datetime) -> datetime:
    """Move a time into working hours (Monday to Friday, 08:00-18:00 UTC): evenings and weekends wait for the morning."""
    while True:
        if ts.weekday() >= 5:
            ts = (ts + timedelta(days=7 - ts.weekday())).replace(hour=8, minute=0)
        elif ts.hour < 8:
            ts = ts.replace(hour=8, minute=0)
        elif ts.hour >= 18:
            ts = (ts + timedelta(days=1)).replace(hour=8, minute=0)
        else:
            return ts.replace(second=0, microsecond=0)


def generate(cases: int = CASES, seed: int = 26) -> list[Event]:
    rng = random.Random(seed)
    u = rng.random

    def wait(mean_hours):  # exponential waiting time
        return timedelta(hours=-mean_hours * math.log(1 - u()))

    def minutes(lo, hi):
        return timedelta(minutes=lo + int((hi - lo) * u()))

    events: list[Event] = []
    for i in range(1, cases + 1):
        cid = f"PR-{i:04d}"
        cat = list(CATEGORIES)[int(u() * len(CATEGORIES))]
        lo, hi = CATEGORIES[cat]
        amount = round(lo + (hi - lo) * u() ** 1.6, 2)
        requester = REQUESTERS[int(u() * 3)]
        t = working(START + timedelta(days=int(u() * 300), hours=int(u() * 9)))
        case: list[Event] = []

        def add(activity, resource, gap, duration):
            nonlocal t
            start = working(t + gap)
            end = start + duration
            case.append(Event(cid, activity, start, end, resource, amount, cat))
            t = end

        add("Submit request", requester, timedelta(0), minutes(10, 20))
        maverick = amount < THRESHOLD and u() < 0.04  # ordered before anyone approved it
        if maverick:
            add("Place order", BUYER, wait(6), minutes(10, 20))
        rounds = 1 + (u() < 0.18) + (u() < 0.04)  # most requests are approved at the first review
        for k in range(rounds):
            add("Manager review", MANAGER, wait(5), minutes(10, 30))
            if k < rounds - 1:
                add("Request more information", MANAGER, timedelta(minutes=5), minutes(5, 10))
                add("Revise request", requester, wait(20), minutes(10, 25))
                if u() < 0.15:  # sent twice in a row
                    add("Revise request", requester, wait(2), minutes(5, 10))
        if u() < 0.06:
            add("Reject request", MANAGER, timedelta(minutes=5), minutes(1, 5))
            events += case
            continue
        if amount >= THRESHOLD:
            add("Finance review", FINANCE, wait(56), minutes(20, 40))
            if u() < 0.10:
                add("Reject request", FINANCE, timedelta(minutes=5), minutes(1, 5))
                events += case
                continue
        if not maverick:
            add("Place order", BUYER, wait(20), minutes(10, 20))
        add("Receive goods", requester, timedelta(days=3 + 6 * u()), minutes(5, 15))
        if u() < 0.05:  # partial delivery: received twice
            add("Receive goods", requester, timedelta(days=2 + 2 * u()), minutes(5, 15))
        add("Close request", ROBOT, wait(4), minutes(1, 3))
        events += case
    return events


def make_dirty(events: list[Event], seed: int = 7) -> list[list[str]]:
    """The same log as raw CSV rows with the defects `check` looks for. `clean` repairs them all back (see tests).

    Defects: different spellings of an activity name, rows without a case id (extra), swapped start and end,
    exact duplicates (extra), day-first dates (dd/MM/yyyy HH:mm) and a +01:00 offset.
    """
    rng = random.Random(seed)
    rows = [e.row() for e in events]
    spell = {"Manager review": ["manager review", "Manager Review "], "Finance review": ["finance review", " Finance review"],
             "Place order": ["Place Order"]}
    n = len(rows)
    for idx in sorted(rng.sample(range(n), 40)):
        if rows[idx][1] in spell:
            rows[idx][1] = spell[rows[idx][1]][int(rng.random() * len(spell[rows[idx][1]]))]
    for idx in sorted(rng.sample(range(n), 8)):
        rows[idx][2], rows[idx][3] = rows[idx][3], rows[idx][2]
    for idx in sorted(rng.sample(range(n), 14)):
        for col in (2, 3):
            if rows[idx][col]:
                d = datetime.strptime(rows[idx][col], "%Y-%m-%d %H:%M:%S")
                rows[idx][col] = d.strftime("%d/%m/%Y %H:%M")
    for idx in sorted(rng.sample(range(n), 10)):
        for col in (2, 3):
            if rows[idx][col] and "/" not in rows[idx][col]:
                d = datetime.strptime(rows[idx][col], "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)
                rows[idx][col] = d.strftime("%Y-%m-%dT%H:%M:%S") + "+01:00"
    extra = [["", "Manager review", "2026-03-02 09:00:00", "2026-03-02 09:10:00", "Sam Demo", "100.00", "Services"]] * 3
    dupes = [list(rows[i]) for i in sorted(rng.sample(range(n), 12))]
    out = rows + extra + dupes
    rng.shuffle(out)
    return out
