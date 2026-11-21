#!/usr/bin/env python3
"""perf-compare: put the Performance Analyzer numbers of the before and the after report side by side.

Performance Analyzer (Optimize ribbon > Performance Analyzer > Start recording > Refresh visuals) lists a duration in
ms for every visual. Type the numbers into a CSV (one row per visual, same page and visual in both reports) and run:

    python perf_compare.py results/performance-analyzer.csv

Columns: page, visual, before_ms, after_ms. A visual that exists in only one report gets an empty cell on the other side
and is listed, not compared. Learn: the durations include time spent queued behind other visuals on the same thread,
so record each report the same way (same slicers, a cleared pane, cold and warm runs labelled in the file name).
Exit 1 when a cell isn't a number, or when a compared visual got slower.
"""
import csv
import sys
from pathlib import Path


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def number(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"not a number: {text!r}")


def compare(rows):
    """[(page, visual, before, after, ratio or None)] and the list of problems."""
    out, problems = [], []
    for r in rows:
        try:
            b, a = number(r["before_ms"]), number(r["after_ms"])
        except ValueError as e:
            problems.append(f"{r['page']}/{r['visual']}: {e}")
            continue
        ratio = b / a if b and a else None
        if ratio is not None and ratio < 1:
            problems.append(f"{r['page']}/{r['visual']}: slower after ({b:g} ms -> {a:g} ms)")
        out.append((r["page"], r["visual"], b, a, ratio))
    return out, problems


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print("usage: perf_compare.py <csv with page,visual,before_ms,after_ms>", file=sys.stderr)
        return 2
    rows, problems = compare(load(sys.argv[1]))
    print(f"{'page':<12}{'visual':<16}{'before ms':>10}{'after ms':>10}{'faster':>9}")
    for page, visual, b, a, ratio in rows:
        cell = lambda v: f"{v:g}" if v is not None else "-"
        print(f"{page:<12}{visual:<16}{cell(b):>10}{cell(a):>10}{(f'{ratio:.1f}x' if ratio else '-'):>9}")
    both = [(b, a) for _, _, b, a, _ in rows if b is not None and a is not None]
    if both:
        tb, ta = sum(b for b, _ in both), sum(a for _, a in both)
        print(f"{'total':<28}{tb:>10g}{ta:>10g}{tb / ta:>8.1f}x   (visuals measured in both reports)")
    for p in problems:
        print("PROBLEM", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
