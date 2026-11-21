#!/usr/bin/env python3
"""Compare the extensions installed in VS Code with the workspace's .vscode/extensions.json.

  python3 tools/ext_audit.py                     # report, exit 1 if something is missing or unwanted
  python3 tools/ext_audit.py --install           # install what's missing (code --install-extension ...)
  python3 tools/ext_audit.py --installed-file x  # use a saved `code --list-extensions --show-versions` output
  python3 tools/ext_audit.py --json              # machine-readable report

Recommendations only *suggest*; this makes onboarding a one-liner and lets a script check a machine.
It never uninstalls anything: unwanted extensions are reported, the developer decides.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$", re.IGNORECASE)


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas, leaving string contents alone.

    VS Code writes extensions.json with comments (JSON with Comments), so json.loads() fails on the
    file VS Code itself generates. A regex would also eat the '//' inside "https://..." strings.
    """
    out, i, n = [], 0, len(text)
    in_string = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
        elif c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_recommendations(path: Path) -> tuple[list[str], list[str]]:
    data = json.loads(strip_jsonc(path.read_text(encoding="utf-8-sig")))
    rec = data.get("recommendations", [])
    unwanted = data.get("unwantedRecommendations", [])
    bad = [x for x in [*rec, *unwanted] if not isinstance(x, str) or not ID_RE.match(x)]
    if bad:
        raise ValueError(f"not a publisher.name extension id: {bad}")
    return rec, unwanted


def parse_installed(listing: str) -> dict[str, str]:
    """`code --list-extensions --show-versions` lines (publisher.name@1.2.3) -> {lower-case id: version}."""
    installed = {}
    for line in listing.splitlines():
        line = line.strip()
        if not line or not ID_RE.match(line.split("@", 1)[0]):
            continue  # skip banners/warnings some builds print
        ext_id, _, version = line.partition("@")
        installed[ext_id.lower()] = version
    return installed


@dataclass
class Report:
    missing: list[str] = field(default_factory=list)
    unwanted_installed: list[str] = field(default_factory=list)
    ok: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.missing and not self.unwanted_installed


def audit(recommended: list[str], unwanted: list[str], installed: dict[str, str]) -> Report:
    # Extension ids are compared case-insensitively: recommendations are often typed in lower case,
    # while --list-extensions prints the publisher's casing (e.g. EditorConfig.EditorConfig).
    report = Report()
    for ext in recommended:
        version = installed.get(ext.lower())
        if version is None:
            report.missing.append(ext)
        else:
            report.ok.append(f"{ext}@{version}")
    report.unwanted_installed = [e for e in unwanted if e.lower() in installed]
    return report


def run_code(code: str, *args: str) -> str:
    exe = shutil.which(code)
    if not exe:
        raise FileNotFoundError(f"'{code}' is not on PATH (macOS: Command Palette > Shell Command: Install 'code' command in PATH)")
    r = subprocess.run([exe, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{code} {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"ext_audit: {e}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workspace", default=".", help="folder that contains .vscode/extensions.json")
    p.add_argument("--code", default="code", help="CLI to call: code, code-insiders, codium")
    p.add_argument("--installed-file", help="saved output of code --list-extensions --show-versions")
    p.add_argument("--install", action="store_true", help="install missing recommendations")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    a = p.parse_args(argv)

    rec_file = Path(a.workspace) / ".vscode" / "extensions.json"
    recommended, unwanted = load_recommendations(rec_file)
    listing = (Path(a.installed_file).read_text() if a.installed_file
               else run_code(a.code, "--list-extensions", "--show-versions"))
    report = audit(recommended, unwanted, parse_installed(listing))

    if a.install and report.missing:
        args = [arg for ext in report.missing for arg in ("--install-extension", ext)]
        print(run_code(a.code, *args).strip())
        report = audit(recommended, unwanted, parse_installed(run_code(a.code, "--list-extensions", "--show-versions")))

    if a.json:
        print(json.dumps({**asdict(report), "clean": report.clean}, indent=2))
    else:
        for line in report.ok:
            print(f"  ok        {line}")
        for ext in report.missing:
            print(f"  MISSING   {ext}")
        for ext in report.unwanted_installed:
            print(f"  UNWANTED  {ext}  (installed; the team asked not to use it)")
        print(f"{len(report.ok)}/{len(recommended)} recommended installed, "
              f"{len(report.missing)} missing, {len(report.unwanted_installed)} unwanted")
    return 0 if report.clean else 1


if __name__ == "__main__":
    sys.exit(main())
