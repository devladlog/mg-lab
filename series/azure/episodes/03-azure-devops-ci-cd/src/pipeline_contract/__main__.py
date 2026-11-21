"""CLI: python -m pipeline_contract pipelines/azure-pipelines.yml [--approval-env contoso-prod ...]"""
from __future__ import annotations

import argparse
import pathlib
import sys

from .contract import check


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline_contract")
    ap.add_argument("pipeline", type=pathlib.Path)
    ap.add_argument("--approval-env", action="append", default=[],
                    help="environment that has an approval check (repeatable)")
    args = ap.parse_args(argv)
    report = check(args.pipeline, set(args.approval_env))
    for line in report.graph():
        print(line)
    for p in report.problems:
        print(f"FAIL {p}")
    print(f"{len(report.files)} files, {len(report.stages)} stages, {len(report.problems)} problems")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
