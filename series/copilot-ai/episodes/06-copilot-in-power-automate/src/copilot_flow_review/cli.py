from __future__ import annotations

import argparse
import json
import sys

from .expressions import check_expression
from .findings import Finding, worst
from pathlib import Path

from .flows import definition_of, load_flow, review_flow
from .prompts import lint_prompt


def _print(findings: list[Finding], as_json: bool, label: str) -> None:
    if as_json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
        return
    if not findings:
        print(f"OK  {label}: nothing found")
    for f in findings:
        print(f)
    errors = sum(f.severity == "error" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    infos = sum(f.severity == "info" for f in findings)
    print(f"\n{label}: {errors} errors, {warnings} warnings, {infos} notes")


def _flow(path: str, as_json: bool) -> int:
    target = Path(path)
    if not target.is_dir():
        findings = review_flow(load_flow(target))
        _print(findings, as_json, path)
        return 1 if worst(findings) == "error" else 0
    # a folder: every Workflows/*.json of an unpacked solution that is a flow (the .data.xml files and other JSON are skipped)
    exit_code, reviewed = 0, 0
    for f in sorted(target.rglob("*.json")):
        try:
            flow = load_flow(f)
            definition_of(flow)
        except (ValueError, json.JSONDecodeError):
            continue
        findings = review_flow(flow)
        _print(findings, as_json, str(f))
        reviewed += 1
        if worst(findings) == "error":
            exit_code = 1
    if reviewed == 0:
        raise ValueError(f"No flow definitions (properties.definition) found under {path}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copilot_flow_review",
        description="Review what you give to Copilot in Power Automate, and what it gives back.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("prompt", help="lint a prompt against the advice on Microsoft Learn")
    sp.add_argument("text")
    sp.add_argument("--mode", choices=["create", "edit"], default="create",
                    help="create = first prompt on the Home page, edit = message in the designer's Copilot pane")
    sp.add_argument("--json", action="store_true")

    sf = sub.add_parser("flow", help="review a flow definition JSON (solution Workflows file, bare definition, or a folder of them)")
    sf.add_argument("path")
    sf.add_argument("--json", action="store_true")

    se = sub.add_parser("expr", help="static check of one expression")
    se.add_argument("expression")
    se.add_argument("--json", action="store_true")

    a = p.parse_args(argv)
    try:
        if a.cmd == "prompt":
            findings, label = lint_prompt(a.text, a.mode), f"prompt ({a.mode})"
        elif a.cmd == "flow":
            return _flow(a.path, a.json)
        else:
            findings, label = check_expression(a.expression), "expression"
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _print(findings, a.json, label)
    return 1 if worst(findings) == "error" else 0
