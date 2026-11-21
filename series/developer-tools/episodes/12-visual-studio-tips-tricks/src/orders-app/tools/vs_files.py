#!/usr/bin/env python3
"""Checks and uses the files Visual Studio reads from a repository.

  vs_files.py check [ROOT] [--known-ids FILE]   validate .vsconfig, *.slnf, *.runsettings, *.playlist,
                                                  launchSettings.json and *.snippet under ROOT (default: .)
  vs_files.py expand SNIPPET [--set ID=VALUE ...] [--selected TEXT]
                                                prints the code a snippet inserts (defaults, replacements,
                                                $selected$ and $end$ as Visual Studio documents them)

`check` exits 1 when it finds a problem, so it can run in a pipeline next to the build. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SNIPPET_NS = {"s": "http://schemas.microsoft.com/VisualStudio/2005/CodeSnippet"}
SKIP_DIRS = {"bin", "obj", "node_modules", ".git", ".vs", "TestResults"}
RESERVED = {"selected", "end"}
COMMANDS = {"Project", "Executable", "IISExpress", "IIS"}


def files(root: Path, pattern: str):
    for path in sorted(root.rglob(pattern)):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


def load_json(path: Path, problems: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        problems.append(f"{path}: not valid JSON ({error})")
        return None


def load_xml(path: Path, problems: list[str]):
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        problems.append(f"{path}: not well-formed XML ({error})")
        return None


def solution_projects(solution: Path) -> set[str]:
    """Project paths listed in a .slnx (Path="...") or .sln (Project(...) = "name", "path", ...) file."""
    text = solution.read_text(encoding="utf-8-sig")
    if solution.suffix == ".slnx":
        found = re.findall(r'<Project\s+Path="([^"]+)"', text)
    else:
        found = re.findall(r'^Project\("[^"]+"\)\s*=\s*"[^"]*",\s*"([^"]+)"', text, re.MULTILINE)
    return {item.replace("\\", "/") for item in found}


def check_vsconfig(path: Path, known: set[str] | None, problems: list[str]) -> None:
    data = load_json(path, problems)
    if data is None:
        return
    if data.get("version") != "1.0":
        problems.append(f'{path}: "version" must be "1.0"')
    components = data.get("components")
    if not isinstance(components, list) or not components:
        problems.append(f'{path}: "components" must be a non-empty array')
        return
    if not all(isinstance(item, str) for item in components):
        problems.append(f"{path}: every component must be a string ID")
        return
    for item in sorted({c for c in components if components.count(c) > 1}):
        problems.append(f"{path}: {item} is listed more than once")
    if known is not None:
        for item in components:
            if item not in known:
                problems.append(f"{path}: {item} is not a workload or component ID in the list you gave")
    if not any(p.suffix in (".sln", ".slnx", ".slnf") for p in path.parent.iterdir()):
        problems.append(f"{path}: Visual Studio only offers missing components when .vsconfig sits next to the solution")


def check_slnf(path: Path, problems: list[str]) -> None:
    data = load_json(path, problems)
    if data is None:
        return
    solution = data.get("solution") or {}
    solution_path = (path.parent / str(solution.get("path", "")).replace("\\", "/")).resolve()
    if not solution_path.is_file():
        problems.append(f"{path}: solution path {solution.get('path')!r} does not exist")
        return
    listed = solution_projects(solution_path)
    projects = solution.get("projects") or []
    if not projects:
        problems.append(f"{path}: no projects: the filter would load and build nothing")
    for project in projects:
        normal = project.replace("\\", "/")
        if normal not in listed:
            problems.append(f"{path}: {project} is not a project of {solution_path.name}")
        elif not (solution_path.parent / normal).is_file():
            problems.append(f"{path}: {project} does not exist on disk")


def check_runsettings(path: Path, problems: list[str]) -> None:
    root = load_xml(path, problems)
    if root is None:
        return
    if root.tag != "RunSettings":
        problems.append(f"{path}: root element must be RunSettings, found {root.tag}")
        return
    run = root.find("RunConfiguration")
    if run is None:
        return
    if run.find("MaxCPUCount") is not None:
        problems.append(f"{path}: MaxCPUCount is ignored; the element is MaxCpuCount (case sensitive)")
    for tag in ("TestSessionTimeout", "MaxCpuCount"):
        node = run.find(tag)
        if node is not None and not (node.text or "").strip().isdigit():
            problems.append(f"{path}: {tag} must be a whole number of milliseconds or processes")
    timeout = run.find("TestSessionTimeout")
    if timeout is not None and (timeout.text or "").strip() == "0":
        problems.append(f"{path}: TestSessionTimeout must be greater than 0")


def check_playlist(path: Path, problems: list[str]) -> None:
    root = load_xml(path, problems)
    if root is None:
        return
    if root.tag != "Playlist" or root.get("Version") != "2.0":
        problems.append(f'{path}: expected <Playlist Version="2.0">')


def playlist_traits(path: Path) -> list[tuple[str, str]]:
    """(name, value) pairs from Trait properties written the way Learn shows for xUnit: "Category [Smoke]"."""
    pairs = []
    for node in ET.parse(path).getroot().iter("Property"):
        match = re.fullmatch(r"(\S+) \[(.+)\]", node.get("Value", "")) if node.get("Name") == "Trait" else None
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def check_launch_settings(path: Path, problems: list[str]) -> None:
    data = load_json(path, problems)
    if data is None:
        return
    urls: dict[str, str] = {}
    for name, profile in (data.get("profiles") or {}).items():
        if profile.get("commandName") not in COMMANDS:
            problems.append(f"{path}: profile {name!r} has commandName {profile.get('commandName')!r}")
        for url in str(profile.get("applicationUrl", "")).split(";"):
            if url and url in urls:
                problems.append(f"{path}: profiles {urls[url]!r} and {name!r} both use {url}")
            elif url:
                urls[url] = name


def snippet_parts(path: Path):
    root = ET.parse(path).getroot()
    snippet = root.find("s:CodeSnippet/s:Snippet", SNIPPET_NS)
    code = snippet.find("s:Code", SNIPPET_NS)
    delimiter = code.get("Delimiter", "$")
    literals = {}
    for literal in snippet.findall("s:Declarations/s:Literal", SNIPPET_NS):
        literals[literal.findtext("s:ID", "", SNIPPET_NS).strip()] = literal.findtext("s:Default", "", SNIPPET_NS).strip()
    return code.text or "", delimiter, literals, root


def check_snippet(path: Path, shortcuts: dict[str, Path], problems: list[str]) -> None:
    if load_xml(path, problems) is None:
        return
    try:
        text, delimiter, literals, root = snippet_parts(path)
    except AttributeError:
        problems.append(f"{path}: needs CodeSnippet/Snippet/Code")
        return
    used = set(re.findall(re.escape(delimiter) + r"(\w+)" + re.escape(delimiter), text))
    for name in sorted(used - RESERVED - set(literals)):
        problems.append(f"{path}: {delimiter}{name}{delimiter} is used in the code but not declared")
    for name in sorted(set(literals) - used):
        problems.append(f"{path}: literal {name} is declared but never used")
    for name in RESERVED:
        if text.count(f"{delimiter}{name}{delimiter}") > 1:
            problems.append(f"{path}: {delimiter}{name}{delimiter} appears more than once; Visual Studio only honors the second")
    for name in set(literals) & RESERVED:
        problems.append(f"{path}: {name} is reserved and cannot be a literal ID")
    for literal in root.iterfind(".//s:Literal", SNIPPET_NS):
        if literal.find("s:Default", SNIPPET_NS) is None:
            problems.append(f"{path}: every Literal needs exactly one Default")
    shortcut = root.findtext(".//s:Header/s:Shortcut", "", SNIPPET_NS).strip()
    if shortcut in shortcuts:
        problems.append(f"{path}: shortcut {shortcut!r} is also used by {shortcuts[shortcut].name}")
    elif shortcut:
        shortcuts[shortcut] = path


def check(root: Path, known_ids: Path | None) -> list[str]:
    problems: list[str] = []
    known = None
    if known_ids:
        known = {line.strip() for line in known_ids.read_text().splitlines() if line.strip() and not line.startswith("#")}
    for path in files(root, ".vsconfig"):
        check_vsconfig(path, known, problems)
    for path in files(root, "*.slnf"):
        check_slnf(path, problems)
    for path in files(root, "*.runsettings"):
        check_runsettings(path, problems)
    for path in files(root, "*.playlist"):
        check_playlist(path, problems)
    for path in files(root, "launchSettings.json"):
        check_launch_settings(path, problems)
    shortcuts: dict[str, Path] = {}
    for path in files(root, "*.snippet"):
        check_snippet(path, shortcuts, problems)
    return problems


def expand(path: Path, values: dict[str, str], selected: str = "") -> str:
    """The text Visual Studio inserts: each $id$ becomes its replacement (or Default), $selected$ the selection, $end$ nothing."""
    text, delimiter, literals, _ = snippet_parts(path)
    values = {**literals, **values, "selected": selected, "end": ""}

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return re.sub(re.escape(delimiter) + r"(\w+)" + re.escape(delimiter), replace, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check")
    check_cmd.add_argument("root", nargs="?", default=".", type=Path)
    check_cmd.add_argument(
        "--known-ids",
        type=Path,
        help="text file with one workload/component ID per line",
    )
    expand_cmd = sub.add_parser("expand")
    expand_cmd.add_argument("snippet", type=Path)
    expand_cmd.add_argument("--set", action="append", default=[], metavar="ID=VALUE")
    expand_cmd.add_argument("--selected", default="")
    args = parser.parse_args(argv)

    if args.command == "check":
        root = args.root.resolve()
        problems = check(root, args.known_ids)
        for problem in problems:
            print(problem.replace(f"{root}/", ""))
        print(f"{len(problems)} problem(s)" if problems else "all Visual Studio files are consistent")
        return 1 if problems else 0
    print(expand(args.snippet, dict(item.split("=", 1) for item in args.set), args.selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
