#!/usr/bin/env python3
"""Read VSTest .trx files: print a summary (also to the GitHub job summary) and enforce what "green" means.

    python3 tools/trx_check.py TestResults/*.trx                      # summary; fail on failed tests
    python3 tools/trx_check.py TestResults/sqlserver.trx --min-passed 4 --no-skipped

Why: `dotnet test --filter` that matches nothing exits 0, and a skipped test is not a passed test. The e2e job
asks for the SQL Server tests to have *run*, not just "not failed".
"""
from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET

NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def counts(path: str) -> dict[str, int]:
    root = ET.parse(path).getroot()
    c = root.find("t:ResultSummary/t:Counters", NS)
    if c is None:
        raise ValueError(f"{path}: no ResultSummary/Counters (not a .trx file?)")
    keys = ("total", "executed", "passed", "failed", "error", "timeout", "aborted")
    out = {k: int(c.get(k, 0)) for k in keys}
    # Skipped xUnit tests are written as outcome="NotExecuted", but the Counters element still says
    # notExecuted="0" (seen with VSTest 18.x). total - executed is what actually didn't run.
    out["skipped"] = out["total"] - out["executed"]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("files", nargs="+")
    p.add_argument("--min-passed", type=int, default=0)
    p.add_argument("--no-skipped", action="store_true", help="fail if any test was not executed (skipped)")
    a = p.parse_args(argv)

    total = {k: 0 for k in ("passed", "failed", "skipped")}
    rows, problems = [], []
    for f in a.files:
        c = counts(f)
        bad = c["failed"] + c["error"] + c["timeout"] + c["aborted"]
        rows.append(f"| {os.path.basename(f)} | {c['passed']} | {bad} | {c['skipped']} |")
        total["passed"] += c["passed"]
        total["failed"] += bad
        total["skipped"] += c["skipped"]
    if total["failed"]:
        problems.append(f"{total['failed']} test(s) failed")
    if total["passed"] < a.min_passed:
        problems.append(f"only {total['passed']} passed, expected at least {a.min_passed}")
    if a.no_skipped and total["skipped"]:
        problems.append(f"{total['skipped']} test(s) skipped, expected all to run")

    table = ["| Results | Passed | Failed | Skipped |", "|---|---:|---:|---:|", *rows]
    print("\n".join(table))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Tests\n\n" + "\n".join(table) + "\n\n" + "".join(f"- ✗ {x}\n" for x in problems) + "\n")
    for x in problems:
        print(f"✗ {x}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
