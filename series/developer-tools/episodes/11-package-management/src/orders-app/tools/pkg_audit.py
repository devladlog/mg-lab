#!/usr/bin/env python3
"""Summarise `dotnet package list --format json` for people and for the pipeline.

    python3 tools/pkg_audit.py                         # vulnerable (direct + transitive), exit 1 at "high" or above
    python3 tools/pkg_audit.py --min-severity low
    python3 tools/pkg_audit.py --outdated              # versions behind the latest, grouped by major/minor/patch
    python3 tools/pkg_audit.py --deprecated
    python3 tools/pkg_audit.py --from-json report.json # read a saved report instead of running dotnet
    python3 tools/pkg_audit.py --format azure          # ##vso[task.logissue] lines for Azure Pipelines

It only reads what `dotnet` reports (the NuGet audit sources, e.g. nuget.org's GitHub Advisory data); it never
decides what is vulnerable on its own. Requires the .NET 10 SDK (`dotnet package list`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ["low", "moderate", "high", "critical"]
MODES = {"vulnerable": "--vulnerable", "outdated": "--outdated", "deprecated": "--deprecated"}


@dataclass(frozen=True)
class Finding:
    project: str
    framework: str
    package: str
    resolved: str
    direct: bool
    kind: str  # vulnerable | outdated | deprecated
    severity: str = ""  # vulnerable only (lower case)
    advisory: str = ""  # vulnerable only
    latest: str = ""  # outdated only
    reasons: tuple[str, ...] = ()  # deprecated only
    alternative: str = ""  # deprecated only


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # e.g. "A source could not be reached"

    def at_least(self, severity: str) -> list[Finding]:
        floor = SEVERITIES.index(severity)
        return [f for f in self.findings if f.kind == "vulnerable" and SEVERITIES.index(f.severity) >= floor]


def parse(report: dict, kind: str) -> Report:
    """Turns the JSON of `dotnet package list --format json` into findings. Projects without findings have no
    `frameworks` key at all (observed with SDK 10.0.115), so everything is optional."""
    out = Report(problems=[p.get("text", str(p)) for p in report.get("problems", [])])
    for project in report.get("projects", []):
        name = Path(project["path"]).stem
        for fw in project.get("frameworks", []):
            for direct, key in ((True, "topLevelPackages"), (False, "transitivePackages")):
                for pkg in fw.get(key, []):
                    base = dict(
                        project=name,
                        framework=fw["framework"],
                        package=pkg["id"],
                        resolved=pkg.get("resolvedVersion", ""),
                        direct=direct,
                        kind=kind,
                    )
                    if kind == "vulnerable":
                        for v in pkg.get("vulnerabilities", []):
                            out.findings.append(
                                Finding(**base, severity=v["severity"].lower(), advisory=v["advisoryurl"])
                            )
                    elif kind == "outdated":
                        out.findings.append(Finding(**base, latest=pkg.get("latestVersion", "")))
                    else:
                        alt = pkg.get("alternativePackage") or {}
                        out.findings.append(
                            Finding(
                                **base, reasons=tuple(pkg.get("deprecationReasons", [])), alternative=alt.get("id", "")
                            )
                        )
    return out


def run_dotnet(kind: str, project: str | None) -> dict:
    cmd = ["dotnet", "package", "list", MODES[kind], "--include-transitive", "--format", "json"]
    if kind != "vulnerable":
        cmd.remove("--include-transitive")  # outdated/deprecated of transitive packages isn't actionable
    if project:
        cmd += ["--project", project]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.stdout}{proc.stderr}")
    text = proc.stdout
    return json.loads(text[text.index("{") :])  # restore messages can come first


def gap(current: str, latest: str) -> str:
    """major / minor / patch / other: how far behind a package is (semantic versioning)."""

    def nums(v: str) -> list[int]:
        parts = v.split("-")[0].split(".")
        return [int(p) if p.isdigit() else 0 for p in parts] + [0, 0, 0]

    a, b = nums(current), nums(latest)
    for i, name in enumerate(("major", "minor", "patch")):
        if a[i] != b[i]:
            return name
    return "other"


def why_hint(f: Finding) -> str:
    return "" if f.direct else f"  (transitive: dotnet nuget why {f.project} {f.package})"


def render_text(report: Report, kind: str, min_severity: str) -> str:
    if kind == "vulnerable":
        rows = sorted(report.findings, key=lambda f: (-SEVERITIES.index(f.severity), f.project, f.package))
        if not rows:
            return "No known vulnerabilities in the packages NuGet resolved."
        lines = [
            f"{len(rows)} known vulnerabilities ({len(report.at_least(min_severity))} at {min_severity} or above):"
        ]
        lines += [
            f"  {f.severity.upper():<9} {f.package} {f.resolved} in {f.project} [{f.framework}] "
            f"{'direct' if f.direct else 'transitive'} {f.advisory}{why_hint(f)}"
            for f in rows
        ]
        return "\n".join(lines)
    if kind == "outdated":
        if not report.findings:
            return "Every top-level package is on its latest version."
        by_gap = sorted(
            report.findings, key=lambda f: ("major", "minor", "patch", "other").index(gap(f.resolved, f.latest))
        )
        return "\n".join(
            ["Top-level packages behind the latest version:"]
            + [
                f"  {gap(f.resolved, f.latest):<6} {f.package} {f.resolved} -> {f.latest} in {f.project}"
                for f in by_gap
            ]
        )
    if not report.findings:
        return "No deprecated packages."
    return "\n".join(
        ["Deprecated packages:"]
        + [
            f"  {f.package} {f.resolved} in {f.project}: {', '.join(f.reasons) or 'deprecated'}"
            + (f"; use {f.alternative}" if f.alternative else "")
            for f in report.findings
        ]
    )


def render_markdown(report: Report, kind: str, min_severity: str) -> str:
    if kind != "vulnerable" or not report.findings:
        return render_text(report, kind, min_severity)
    lines = ["| Severity | Package | Resolved | Project | Via | Advisory |", "|---|---|---|---|---|---|"]
    for f in sorted(report.findings, key=lambda f: (-SEVERITIES.index(f.severity), f.package)):
        lines.append(
            f"| {f.severity} | {f.package} | {f.resolved} | {f.project} | "
            f"{'direct' if f.direct else 'transitive'} | {f.advisory} |"
        )
    return "\n".join(lines)


def render_azure(report: Report, kind: str, min_severity: str) -> str:
    """Azure Pipelines logging commands (stdout only; `;` and `]` in values must be escaped)."""

    def esc(text: str) -> str:
        return text.replace("%", "%AZP25").replace(";", "%3B").replace("]", "%5D")

    floor = SEVERITIES.index(min_severity)
    lines = []
    for f in report.findings:
        if kind == "vulnerable":
            level = "error" if SEVERITIES.index(f.severity) >= floor else "warning"
            msg = f"{f.package} {f.resolved} has a known {f.severity} severity vulnerability: {f.advisory}"
        else:
            level, msg = (
                "warning",
                f"{f.package} {f.resolved} is {kind}" + (f" (latest {f.latest})" if f.latest else ""),
            )
        lines.append(f"##vso[task.logissue type={level};code={kind};]{esc(f'{f.project}: {msg}')}")
    return "\n".join(lines)


RENDERERS = {"text": render_text, "markdown": render_markdown, "azure": render_azure}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--outdated", action="store_true")
    mode.add_argument("--deprecated", action="store_true")
    ap.add_argument("--project", help="project, solution or folder (default: the current folder)")
    ap.add_argument(
        "--min-severity",
        choices=SEVERITIES,
        default="high",
        help="vulnerabilities at or above this severity fail the run (default: high)",
    )
    ap.add_argument("--format", choices=sorted(RENDERERS), default="text")
    ap.add_argument("--from-json", metavar="FILE", help="read a saved `--format json` report")
    args = ap.parse_args(argv)

    kind = "outdated" if args.outdated else "deprecated" if args.deprecated else "vulnerable"
    raw = (
        json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        if args.from_json
        else run_dotnet(kind, args.project)
    )
    report = parse(raw, kind)
    for problem in report.problems:
        print(f"warning: {problem}", file=sys.stderr)
    output = RENDERERS[args.format](report, kind, args.min_severity)
    if output:
        print(output)
    if kind == "vulnerable" and report.at_least(args.min_severity):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
