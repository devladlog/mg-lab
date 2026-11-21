#!/usr/bin/env python3
"""Vulnerability gate for a Trivy JSON report (schema version 2).

Fails (exit 1) when the report holds a vulnerability at a blocking severity that has a fix available and is not covered
by a valid, unexpired waiver. Exit 2 means the inputs are unusable (bad report, bad waiver file): never treat that as
a pass. Standard library only, so it runs on any runner.

    python security/vuln_gate.py --report trivy.json --waivers security/waivers.json

Waiver file: {"waivers": [{"id": "CVE-...", "package": "optional", "owner": "...", "reason": "...", "expires": "2026-12-31"}]}
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")
MAX_WAIVER_DAYS = 90


class InputError(Exception):
    """The report or the waiver file cannot be trusted."""


@dataclass(frozen=True)
class Finding:
    vuln_id: str
    package: str
    installed: str
    fixed: str
    severity: str
    target: str


@dataclass(frozen=True)
class Waiver:
    vuln_id: str
    package: str | None
    owner: str
    reason: str
    expires: dt.date

    def matches(self, f: Finding) -> bool:
        return f.vuln_id == self.vuln_id and (self.package is None or self.package == f.package)


@dataclass
class Verdict:
    blocking: list[Finding] = field(default_factory=list)
    waived: list[tuple[Finding, Waiver]] = field(default_factory=list)
    ignored: list[Finding] = field(default_factory=list)       # below the threshold or no fix yet
    expired: list[Waiver] = field(default_factory=list)        # an expired waiver that still matches a finding
    stale: list[Waiver] = field(default_factory=list)          # a waiver that matches nothing any more

    @property
    def passed(self) -> bool:
        return not self.blocking


def load_findings(path: Path) -> list[Finding]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise InputError(f"cannot read report {path}: {e}") from e
    if not isinstance(data, dict) or data.get("SchemaVersion") != 2:
        raise InputError("report is not a Trivy JSON report with SchemaVersion 2")
    results = data.get("Results")
    if results is None:
        # Trivy omits Results when nothing was found in any target.
        return []
    if not isinstance(results, list):
        raise InputError("report has a Results field that is not a list")
    out: list[Finding] = []
    for r in results:
        for v in (r.get("Vulnerabilities") or []):
            sev = str(v.get("Severity", "UNKNOWN")).upper()
            if sev not in SEVERITIES:
                raise InputError(f"unknown severity {sev!r} for {v.get('VulnerabilityID')}")
            vid = v.get("VulnerabilityID")
            if not vid:
                raise InputError("a vulnerability without VulnerabilityID")
            out.append(Finding(vid, v.get("PkgName", "?"), v.get("InstalledVersion", "?"),
                               v.get("FixedVersion") or "", sev, r.get("Target", "?")))
    return out


def load_waivers(path: Path | None, today: dt.date) -> list[Waiver]:
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"cannot parse waivers {path}: {e}") from e
    items = data.get("waivers") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise InputError("waiver file needs a top-level 'waivers' list")
    out: list[Waiver] = []
    for i, w in enumerate(items):
        where = f"waivers[{i}]"
        for key in ("id", "owner", "reason", "expires"):
            if not str(w.get(key, "")).strip():
                raise InputError(f"{where}: '{key}' is required")
        try:
            expires = dt.date.fromisoformat(str(w["expires"]))
        except ValueError as e:
            raise InputError(f"{where}: expires must be YYYY-MM-DD") from e
        if (expires - today).days > MAX_WAIVER_DAYS:
            raise InputError(f"{where}: expires {expires} is more than {MAX_WAIVER_DAYS} days away; waivers are short on purpose")
        out.append(Waiver(w["id"], w.get("package"), w["owner"], w["reason"], expires))
    return out


def evaluate(findings: list[Finding], waivers: list[Waiver], today: dt.date,
             fail_on: set[str], only_fixable: bool = True) -> Verdict:
    v = Verdict()
    used: set[Waiver] = set()
    for f in findings:
        if f.severity not in fail_on or (only_fixable and not f.fixed):
            v.ignored.append(f)
            continue
        match = next((w for w in waivers if w.matches(f)), None)
        if match is None:
            v.blocking.append(f)
        elif match.expires < today:
            used.add(match)
            v.expired.append(match)
            v.blocking.append(f)       # an expired waiver is no waiver
        else:
            used.add(match)
            v.waived.append((f, match))
    v.stale = [w for w in waivers if w not in used]
    return v


def render(v: Verdict, fail_on: set[str], today: dt.date) -> str:
    lines = [f"## Vulnerability gate ({today.isoformat()})", "",
             f"Blocking severities: {', '.join(s for s in reversed(SEVERITIES) if s in fail_on)} (fix available)", ""]
    lines.append("**Result: PASSED**" if v.passed else f"**Result: FAILED, {len(v.blocking)} blocking finding(s)**")
    if v.blocking:
        lines += ["", "| Severity | Id | Package | Installed | Fixed in | Target |", "|---|---|---|---|---|---|"]
        lines += [f"| {f.severity} | {f.vuln_id} | {f.package} | {f.installed} | {f.fixed or '-'} | {f.target} |" for f in v.blocking]
    if v.waived:
        lines += ["", "Waived (time-boxed):"]
        lines += [f"- {f.vuln_id} in {f.package}: {w.reason} (owner {w.owner}, until {w.expires})" for f, w in v.waived]
    if v.expired:
        lines += ["", "Expired waivers still needed by a finding (renew with a new review or fix the package):"]
        lines += [f"- {w.vuln_id}, expired {w.expires}, owner {w.owner}" for w in v.expired]
    if v.stale:
        lines += ["", "Stale waivers (match nothing, delete them):"]
        lines += [f"- {w.vuln_id} ({w.owner})" for w in v.stale]
    lines += ["", f"Not blocking: {len(v.ignored)} finding(s) below the threshold or without a fix yet."]
    return "\n".join(lines) + "\n"


def parse_severities(text: str) -> set[str]:
    wanted = {s.strip().upper() for s in text.split(",") if s.strip()}
    bad = wanted - set(SEVERITIES)
    if bad or not wanted:
        raise InputError(f"--fail-on must be a comma list of {', '.join(SEVERITIES)}")
    return wanted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", required=True, type=Path, help="Trivy JSON report")
    p.add_argument("--waivers", type=Path, help="waiver file (JSON)")
    p.add_argument("--fail-on", default="CRITICAL,HIGH", help="comma list of blocking severities (default CRITICAL,HIGH)")
    p.add_argument("--include-unfixed", action="store_true", help="also block findings that have no fixed version yet")
    p.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests and dry runs")
    a = p.parse_args(argv)
    try:
        today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
        fail_on = parse_severities(a.fail_on)
        findings = load_findings(a.report)
        waivers = load_waivers(a.waivers, today)
    except (InputError, ValueError) as e:
        print(f"vuln_gate: input error: {e}", file=sys.stderr)
        return 2
    verdict = evaluate(findings, waivers, today, fail_on, only_fixable=not a.include_unfixed)
    text = render(verdict, fail_on, today)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    sys.exit(main())
