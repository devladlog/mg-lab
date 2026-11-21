#!/usr/bin/env python3
"""Check record.json files against series/RECORD_BRIEF.md. Usage: check_record.py <episode folders...>"""
import json
import re
import sys
from pathlib import Path

import yaml

SECRET = re.compile(r"(password\s*=|pwd=|\.Password\b|GetNetworkCredential|client_secret\s*=|AccountKey=|sig=|Get-Credential\b(?!s))", re.I)
REAL = re.compile(r"onmicrosoft\.com|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
KINDS = {"terminal", "browser", "app"}


def check(folder: Path) -> list[str]:
    errs = []
    e = lambda m: errs.append(f"{folder.name}: {m}")
    rf, sf = folder / "record.json", folder / "script.yaml"
    if not rf.exists():
        return [f"{folder.name}: missing record.json"]
    try:
        rec = json.loads(rf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as x:
        return [f"{folder.name}: invalid JSON: {x}"]
    script = yaml.safe_load(sf.read_text(encoding="utf-8"))
    want = [Path(s["image"]).stem for s in script.get("scenes", []) if s.get("type") == "screen" and s.get("image")]
    got = [s.get("name") for s in rec.get("screens", [])]
    if sorted(got) != sorted(want):
        e(f"screens {got} != screen scenes in script.yaml {want}")
    for key in ("prepare", "teardown"):
        if key in rec and not isinstance(rec[key], list):
            e(f"{key} must be a list of strings")
    for s in rec.get("screens", []):
        n = s.get("name")
        kind = s.get("kind", "terminal")
        if kind not in KINDS:
            e(f"{n}: kind must be one of {sorted(KINDS)}")
        if kind == "terminal":
            if not s.get("target"):
                e(f"{n}: terminal screen needs target (host or VM name)")
            cmds = s.get("commands") or []
            if not cmds or not all(isinstance(c, str) for c in cmds):
                e(f"{n}: terminal screen needs commands[] (strings)")
            if any(re.match(r"\s*(Write-Host|echo)\s+['\"]", c) for c in cmds):
                e(f"{n}: commands must run real things, not print canned text")
        else:
            if not s.get("steps"):
                e(f"{n}: {kind} screen needs steps[]")
            if kind == "browser" and not s.get("url"):
                e(f"{n}: browser screen needs url")
            if kind == "app" and not s.get("app"):
                e(f"{n}: app screen needs app")
            if "mask" not in s:
                e(f"{n}: {kind} screen needs mask[] (may be empty)")
    text = rf.read_text(encoding="utf-8")
    for m in SECRET.finditer(text):
        e(f"possible secret handling: '{m.group(0)}'")
    if REAL.search(text):
        e("possible real tenant identifier (onmicrosoft.com or a GUID)")
    if not isinstance(rec.get("needs", []), list):
        e("needs must be a list")
    return errs


def main(argv):
    allerrs = []
    for a in argv:
        allerrs += check(Path(a))
    for x in allerrs:
        print("ERROR", x)
    print(f"{len(argv)} folders checked, {len(allerrs)} errors")
    return 1 if allerrs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
