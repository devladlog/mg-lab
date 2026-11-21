"""Pipeline reports: print a grouped report, reconcile the three ways of computing it, write CSV."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import queries as Q
from .webapi import WebApi


def table(report: Q.Report, title: str, out: Callable[[str], None] = print) -> None:
    out(f"{title:<28}{'open':>6}{'estimated value':>18}")
    for key in sorted(report, key=lambda k: (k is None, str(k))):
        g = report[key]
        out(f"{Q.fmt_key(key, g):<28}{g.count:>6}{g.total:>18,.2f}")
    out(f"{'total':<28}{sum(g.count for g in report.values()):>6}{sum(g.total for g in report.values()):>18,.2f}")


def write_csv(report: Q.Report, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "open", "estimated_value"])
        for key in sorted(report, key=lambda k: (k is None, str(k))):
            w.writerow([Q.fmt_key(key, report[key]), report[key].count, f"{report[key].total:.2f}"])


def category_three_ways(api: WebApi, by: str) -> Dict[str, Q.Report]:
    return {
        "client-side rows": Q.from_client_rows(api.get_all(Q.raw_rows(by), annotations=True), by),
        "FetchXML aggregate": Q.from_fetch_rows(Q.run_fetch(api, Q.fetch_by_column(by))),
        "OData $apply": Q.from_apply_rows(Q.run_apply(api, Q.apply_by_column(by)), by),
    }


def month_two_ways(api: WebApi) -> Dict[str, Q.Report]:
    return {
        "client-side rows": Q.from_client_month_rows(api.get_all(Q.raw_rows("estimatedclosedate"))),
        "FetchXML aggregate": Q.from_fetch_month_rows(Q.run_fetch(api, Q.fetch_by_month())),
    }


def reconcile(results: Dict[str, Q.Report], out: Callable[[str], None] = print) -> int:
    """Compare every method with the first one (the rows themselves). Returns the number of disagreeing methods."""
    names = list(results)
    ref = results[names[0]]
    bad = 0
    for name in names[1:]:
        diffs = Q.differences(ref, results[name])
        total = sum(g.total for g in results[name].values())
        if diffs:
            bad += 1
            out(f"MISMATCH {name}: total {total:,.2f}")
            for d in diffs:
                out(f"    {d}")
        else:
            out(f"OK       {name}: {sum(g.count for g in results[name].values())} open, total {total:,.2f}")
    out(f"reference: {names[0]}, total {sum(g.total for g in ref.values()):,.2f}")
    return bad
