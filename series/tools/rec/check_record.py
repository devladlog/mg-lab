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
LOCAL_ONLY = re.compile(r"\baz\s+login\b|\bConnect-\w+|\bpac\s+auth\b|\bRead-Host\b|\bdocker\b|-VMName\b|\$cred\b|\bGet-VM\b|\bdevtunnel\b|\bgh\s+auth\b|\bAdd-PowerAppsAccount\b", re.I)


GOTO = re.compile(r"^.+:\d+(:\d+)?$")


def check_helpers(s: dict) -> list[str]:
    """Blocks read by Start-WtLayout.ps1 (layout), Open-VsCodeScene.ps1 (vscode) and the lead's window.json (window)."""
    m = []
    prep = " ".join(x for x in s.get("prepare") or [] if isinstance(x, str))
    lay = s.get("layout")
    if lay is not None:
        panes = lay.get("panes") or []
        if not lay.get("title"):
            m.append("layout.title missing (window.json title)")
        if len(panes) < 2:
            m.append("layout.panes needs two or more panes")
        titles = [p.get("title") for p in panes]
        for p in panes:
            if not p.get("title") or not p.get("workdir") or not p.get("commands"):
                m.append("every layout pane needs title, workdir and commands[]")
            elif any(re.match(r"\s*(Write-Host|echo)\s+['\"]", c) for c in p["commands"]):
                m.append(f"pane {p['title']}: commands must run real things, not print canned text")
        if lay.get("stopPane") and lay["stopPane"] not in titles:
            m.append(f"layout.stopPane {lay['stopPane']} is not a pane title")
        if "Start-WtLayout.ps1" not in prep:
            m.append("layout without Start-WtLayout.ps1 in the screen prepare")
        if not any("Stop-WtLayout.ps1" in x for x in s.get("teardown") or []):
            m.append("layout without Stop-WtLayout.ps1 in the screen teardown")
    vs = s.get("vscode")
    if vs is not None:
        if not vs.get("folder") or not GOTO.match(str(vs.get("goto", ""))):
            m.append("vscode needs folder and goto (file:line[:column])")
        for t in vs.get("tasks") or []:
            if not t.get("label") or not t.get("command"):
                m.append("every vscode task needs label and command")
        if "Open-VsCodeScene.ps1" not in prep:
            m.append("vscode without Open-VsCodeScene.ps1 in the screen prepare")
    ptr = s.get("pointer")
    if ptr is not None:
        if not isinstance(ptr, list) or not ptr:
            m.append("pointer must be a non-empty list of steps")
        else:
            for st in ptr:
                keys = [k for k in st if k != "glide"] if isinstance(st, dict) else []
                if len(keys) != 1 or keys[0] not in ("wait", "move", "click"):
                    m.append(f"pointer step must be exactly one of wait, move, click: {st}")
                elif keys[0] != "wait" and not (isinstance(st[keys[0]], list) and len(st[keys[0]]) == 2):
                    m.append(f"pointer {keys[0]} needs [x, y]: {st}")
        if not any("Invoke-PointerScript.ps1" in x and "-Start" in x for x in s.get("play") or []):
            m.append("pointer without 'Invoke-PointerScript.ps1 ... -Start' in the screen play list")
        if not s.get("window"):
            m.append("pointer needs a window block (title)")
    w = s.get("window")
    if w is not None:
        for k in ("title", "out"):
            if not w.get(k):
                m.append(f"window.{k} missing")
        if w.get("out") and not str(w["out"]).replace("/", "\\").endswith(f"screens\\{s.get('name')}.mp4"):
            m.append("window.out must end with screens\\<name>.mp4")
        if lay is not None and w.get("title") != lay.get("title"):
            m.append("window.title must be the layout title")
    return m


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
    for key in ("prepare", "teardown", "prepare_local", "teardown_local"):
        if key in rec and not (isinstance(rec[key], list) and all(isinstance(x, str) for x in rec[key])):
            e(f"{key} must be a list of strings")
    # prepare_local / teardown_local run for "screen:" queue lines: laptop-only steps, nothing from the owner
    for key in ("prepare_local", "teardown_local"):
        for st in rec.get(key) or []:
            if isinstance(st, str) and not st.lstrip().startswith("#") and LOCAL_ONLY.search(st):
                e(f"{key} must stay local (no sign-in, prompt, Docker or VM): '{st[:80]}'")
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
            errs.extend(f"{folder.name}: {n}: {m}" for m in check_helpers(s))
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
