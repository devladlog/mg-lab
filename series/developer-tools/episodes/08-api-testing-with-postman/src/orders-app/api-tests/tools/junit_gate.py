#!/usr/bin/env python3
"""Fail when a Newman JUnit report says "green" but proves too little.

    python3 tools/junit_gate.py results/junit-main.xml --min-tests 30

Newman exits 0 when a collection has no tests at all, and when a folder filter matches nothing it just
runs nothing. A pipeline that only looks at the exit code would call both a pass. This counts the
assertions that actually ran (every pm.test() is one <testcase>) and exits 1 when there are failures,
errors, fewer than --min-tests, or more than --max-skipped skipped. Standard library only.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def summarize(path: str) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = [c for c in cases if c.find("skipped") is not None]
    return {
        "total": len(cases),
        "failed": [(c.get("classname", ""), c.get("name", "")) for c in failed],
        "skipped": len(skipped),
        "passed": len(cases) - len(failed) - len(skipped),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", help="JUnit XML written by newman --reporters junit")
    ap.add_argument("--min-tests", type=int, default=1, help="fail if fewer assertions ran (default 1)")
    ap.add_argument("--max-skipped", type=int, default=0)
    a = ap.parse_args(argv)

    try:
        s = summarize(a.report)
    except (OSError, ET.ParseError) as e:
        print(f"✗ cannot read {a.report}: {e}")
        return 1

    problems = []
    if s["failed"]:
        problems += [f"failed: {n}" for _, n in s["failed"]]
    if s["total"] < a.min_tests:
        problems.append(f"only {s['total']} assertions ran, expected at least {a.min_tests}")
    if s["skipped"] > a.max_skipped:
        problems.append(f"{s['skipped']} skipped, allowed {a.max_skipped}")

    print(f"{a.report}: {s['passed']} passed, {len(s['failed'])} failed, {s['skipped']} skipped, {s['total']} total")
    for p in problems:
        print(f"✗ {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
