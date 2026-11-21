"""The numbers the process mining dashboard should show, computed locally from the same CSV.

Metric definitions follow Learn (Visualize and gain insights from processes): variants are unique sequences from start to
finish; self-loop = an activity directly followed by itself; loop = repeated, but not directly; rework = either.
Where Learn doesn't define a number precisely (how a transition's duration is measured), the choice is ours and marked:
the recording session compares our numbers with the service's and the README says what differs.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from .eventlog import Event


def _cases(events: list[Event]) -> dict[str, list[Event]]:
    cases: dict[str, list[Event]] = defaultdict(list)
    for i, e in sorted(enumerate(events), key=lambda p: (p[1].start, p[0])):  # ties keep file order
        cases[e.case_id].append(e)
    return cases


def _hours(delta) -> float:
    return delta.total_seconds() / 3600


def analyze(events: list[Event], top: int = 5, min_cases: int = 20) -> dict:
    cases = _cases(events)
    durations, variants = {}, Counter()
    self_loop, loop = set(), set()
    act_count, act_cases, act_max, act_dur = Counter(), Counter(), Counter(), defaultdict(list)
    trans_count, trans_wait = Counter(), defaultdict(list)
    for cid, evs in cases.items():
        names = [e.activity for e in evs]
        variants[tuple(names)] += 1
        durations[cid] = _hours(max(e.end or e.start for e in evs) - min(e.start for e in evs))
        per = Counter(names)
        for a, n in per.items():
            act_count[a] += n
            act_cases[a] += 1
            act_max[a] = max(act_max[a], n)
        for e in evs:
            if e.end:
                act_dur[e.activity].append(_hours(e.end - e.start))
        for a, b in zip(evs, evs[1:]):
            trans_count[(a.activity, b.activity)] += 1
            trans_wait[(a.activity, b.activity)].append(_hours(b.start - (a.end or a.start)))  # ours: next start - previous end
            if a.activity == b.activity:
                self_loop.add(cid)
        # loop: an activity that comes back after at least one other activity in between
        last_seen = {}
        for i, n in enumerate(names):
            if n in last_seen and i - last_seen[n] > 1:
                loop.add(cid)
            last_seen[n] = i
    n_cases = len(cases)
    vals = sorted(durations.values())
    pct = lambda k: round(100 * k / n_cases, 1) if n_cases else 0.0
    transitions = {f"{a} > {b}": {"count": c, "mean_wait_h": round(statistics.mean(trans_wait[(a, b)]), 1),
                                  "total_wait_h": round(sum(trans_wait[(a, b)]), 1)}
                   for (a, b), c in trans_count.items()}
    # a transition seen in a handful of cases says little: rank only those with enough support
    ranked = sorted(((k, v) for k, v in transitions.items() if v["count"] >= min_cases),
                    key=lambda kv: kv[1]["mean_wait_h"], reverse=True)
    worst = ranked[0] if ranked else None
    return {
        "cases": n_cases, "events": len(events), "activities": len(act_count), "variants": len(variants),
        "resources": len({e.resource for e in events if e.resource}),
        "avg_case_duration_h": round(statistics.mean(vals), 1) if vals else 0.0,
        "median_case_duration_h": round(statistics.median(vals), 1) if vals else 0.0,
        "self_loop_cases_pct": pct(len(self_loop)), "loop_cases_pct": pct(len(loop)),
        "rework_cases_pct": pct(len(self_loop | loop)),
        "top_variants": [{"count": c, "pct": pct(c), "path": list(v)} for v, c in variants.most_common(top)],
        "activity_stats": {a: {"total_count": act_count[a], "case_count": act_cases[a], "max_in_case": act_max[a],
                               "mean_duration_min": round(60 * statistics.mean(act_dur[a]), 1) if act_dur[a] else None}
                           for a in sorted(act_count)},
        "transitions": transitions,
        "slowest_transition": {"name": worst[0], **worst[1]} if worst else None,
        "slowest_transitions": [{"name": k, **v} for k, v in ranked[:3]],
    }


def precedence_violations(events: list[Event], before: str, after: str) -> list[str]:
    """Cases where `after` happened before the first `before` (or `before` never happened): a compliance check."""
    bad = []
    for cid, evs in _cases(events).items():
        starts_b = [e.start for e in evs if e.activity == before]
        starts_a = [e.start for e in evs if e.activity == after]
        if starts_a and (not starts_b or min(starts_a) < min(starts_b)):
            bad.append(cid)
    return sorted(bad)
