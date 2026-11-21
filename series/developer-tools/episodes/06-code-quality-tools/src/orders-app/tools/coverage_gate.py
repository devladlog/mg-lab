#!/usr/bin/env python3
"""Coverage gate for Cobertura reports: overall line coverage of the product code, and coverage of the lines a
pull request changed ("diff coverage").

    dotnet test --collect "Code Coverage;Format=cobertura" --results-directory TestResults
    python3 tools/coverage_gate.py TestResults --include src/ --min-line 90
    python3 tools/coverage_gate.py TestResults --include src/ --min-line 90 --diff-base origin/main --min-diff 80

Why diff coverage: a total of 90 % says little about the 12 lines this PR added. Changed lines that no test
executed are listed, written to the GitHub job summary and annotated on the PR diff (`::warning file=...`).
Lines a report doesn't list (comments, braces, declarations) aren't coverable and don't count.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Coverage:
    """hits[(relative path, line)] = highest hit count seen across classes, methods and reports."""

    hits: dict[tuple[str, int], int] = field(default_factory=dict)

    def add(self, path: str, line: int, count: int) -> None:
        key = (path, line)
        self.hits[key] = max(self.hits.get(key, 0), count)

    def files(self) -> set[str]:
        return {p for p, _ in self.hits}

    def lines(self, prefixes: list[str]) -> dict[tuple[str, int], int]:
        return {k: v for k, v in self.hits.items() if any(k[0].startswith(p) for p in prefixes)}


def find_reports(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            found += sorted(p.rglob("*.cobertura.xml"))
        elif p.is_file():
            found.append(p)
    return found


def relative(path: str, root: Path) -> str:
    """Reports hold absolute paths of the machine that ran the tests; compare them repo-relative."""
    p = Path(path)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def load(reports: list[Path], root: Path) -> Coverage:
    cov = Coverage()
    for report in reports:
        tree = ET.parse(report)
        for cls in tree.getroot().iter("class"):
            path = relative(cls.get("filename", ""), root)
            for line in cls.iter("line"):
                cov.add(path, int(line.get("number")), int(line.get("hits", "0")))
    return cov


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str) -> dict[str, set[int]]:
    """Added or modified lines per file, from `git diff --unified=0` output."""
    out: dict[str, set[int]] = {}
    current = None
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current = None if target == "/dev/null" else target.removeprefix("b/")
            if current:
                out.setdefault(current, set())
        elif current and (m := HUNK.match(raw)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            out[current].update(range(start, start + count))
    return out


def git_diff(base: str, root: Path, prefixes: list[str]) -> str:
    cmd = ["git", "diff", "--unified=0", "--no-color", "--no-ext-diff", f"{base}...HEAD", "--", *prefixes]
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True).stdout


def ranges(numbers: list[int]) -> str:
    out, start, prev = [], None, None
    for n in sorted(numbers) + [None]:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = n
    return ", ".join(out)


@dataclass
class Result:
    total: tuple[int, int]  # covered, coverable
    diff: tuple[int, int] | None = None
    uncovered_changed: dict[str, list[int]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def pct(covered: int, coverable: int) -> float:
    return 100.0 if coverable == 0 else 100.0 * covered / coverable


def evaluate(
    cov: Coverage,
    prefixes: list[str],
    min_line: float,
    changed: dict[str, set[int]] | None = None,
    min_diff: float | None = None,
) -> Result:
    product = cov.lines(prefixes)
    if not product:
        return Result((0, 0), problems=[f"no covered files under {', '.join(prefixes)}: wrong --include or no report?"])
    covered = sum(1 for v in product.values() if v > 0)
    res = Result((covered, len(product)))
    if pct(*res.total) < min_line:
        res.problems.append(f"line coverage {pct(*res.total):.1f}% is below {min_line:g}%")
    if changed is not None:
        hit = total = 0
        for path, lines in sorted(changed.items()):
            coverable = [n for n in lines if (path, n) in product]
            missed = sorted(n for n in coverable if product[(path, n)] == 0)
            total += len(coverable)
            hit += len(coverable) - len(missed)
            if missed:
                res.uncovered_changed[path] = missed
        res.diff = (hit, total)
        if min_diff is not None and pct(hit, total) < min_diff:
            res.problems.append(
                f"diff coverage {pct(hit, total):.1f}% ({hit}/{total} changed lines) is below {min_diff:g}%"
            )
    return res


def report(res: Result, annotate: bool) -> str:
    lines = [
        "| Coverage | Lines | % |",
        "|---|---:|---:|",
        f"| product code | {res.total[0]}/{res.total[1]} | {pct(*res.total):.1f} |",
    ]
    if res.diff is not None:
        lines.append(f"| changed lines | {res.diff[0]}/{res.diff[1]} | {pct(*res.diff):.1f} |")
    for path, missed in res.uncovered_changed.items():
        lines.append(f"\nNot covered, changed in this PR: `{path}` lines {ranges(missed)}")
        if annotate:  # GitHub shows these on the "Files changed" tab of the PR
            for n in missed:
                print(f"::warning file={path},line={n},title=Not covered::Changed line not executed by any test")
    lines += [f"- ✗ {p}" for p in res.problems]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("reports", nargs="+", help="Cobertura files or folders to search for *.cobertura.xml")
    p.add_argument("--include", action="append", default=None, help="repo-relative path prefix (default: src/)")
    p.add_argument("--min-line", type=float, default=0)
    p.add_argument("--diff-base", help="git ref to compare with, e.g. origin/main (needs full history)")
    p.add_argument("--min-diff", type=float)
    p.add_argument("--root", default=".", help="repository root (default: current folder)")
    a = p.parse_args(argv)

    root, prefixes = Path(a.root), a.include or ["src/"]
    reports = find_reports(a.reports)
    if not reports:
        print("✗ no Cobertura report found", file=sys.stderr)
        return 1
    cov = load(reports, root)
    changed = changed_lines(git_diff(a.diff_base, root, prefixes)) if a.diff_base else None
    res = evaluate(cov, prefixes, a.min_line, changed, a.min_diff)
    text = report(res, annotate=os.environ.get("GITHUB_ACTIONS") == "true")
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Coverage\n\n" + text + "\n\n")
    return 1 if res.problems else 0


if __name__ == "__main__":
    sys.exit(main())
