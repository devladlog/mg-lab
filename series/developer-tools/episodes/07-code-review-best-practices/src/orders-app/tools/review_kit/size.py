"""How big is this pull request, for a reviewer? Lines that a person has to read, per area, and a size label."""
from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass, field

# Files a reviewer shouldn't have to read line by line: lock files, generated code, snapshots, vendored code.
DEFAULT_IGNORES = (
    "*.lock", "package-lock.json", "packages.lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
    "*.g.cs", "*.Designer.cs", "*.min.js", "*.min.css", "*.snap", "*.verified.*",
    "node_modules/*", "vendor/*", "*/node_modules/*", "*/vendor/*",
)
# Team defaults, not a standard: changed lines (added + deleted) that a person reads. Change them in one place.
DEFAULT_LIMITS = (("S", 100), ("M", 300), ("L", 600))      # above the last limit: XL


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int
    binary: bool = False
    renamed_from: str | None = None

    @property
    def lines(self) -> int:
        return self.added + self.deleted


@dataclass
class SizeReport:
    counted: list[FileChange] = field(default_factory=list)
    ignored: list[FileChange] = field(default_factory=list)
    label: str = "S"

    @property
    def lines(self) -> int:
        return sum(f.lines for f in self.counted)

    def by_area(self) -> list[tuple[str, int, int]]:
        """(area, files, lines), biggest first. The area is the first two path segments (src/Contoso.Orders.Api)."""
        areas: dict[str, list[int]] = {}
        for f in self.counted:
            parts = f.path.split("/")
            key = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if len(parts) == 2 else "(repo root)")
            files, lines = areas.setdefault(key, [0, 0])
            areas[key] = [files + 1, lines + f.lines]
        return sorted(((k, v[0], v[1]) for k, v in areas.items()), key=lambda t: (-t[2], t[0]))


def is_ignored(path: str, patterns=DEFAULT_IGNORES) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def label_for(lines: int, limits=DEFAULT_LIMITS) -> str:
    for name, limit in limits:
        if lines <= limit:
            return name
    return "XL"


def parse_numstat_z(raw: str) -> list[FileChange]:
    """`git diff --numstat -z -M`: `added<TAB>deleted<TAB>path<NUL>`, and for a rename `added<TAB>deleted<TAB><NUL>old<NUL>new<NUL>`."""
    out, parts, i = [], raw.split("\0"), 0
    while i < len(parts) and parts[i]:
        added, deleted, path = parts[i].split("\t", 2)
        old = None
        if path == "":                                         # rename: the next two records are old and new path
            old, path = parts[i + 1], parts[i + 2]
            i += 2
        binary = added == "-" and deleted == "-"
        out.append(FileChange(path, 0 if binary else int(added), 0 if binary else int(deleted), binary, old))
        i += 1
    return out


def diff_numstat(base: str, head: str, cwd: str | None = None) -> list[FileChange]:
    """Three dots: the changes on `head` since it left `base` (what a pull request shows), not base's own progress."""
    proc = subprocess.run(["git", "diff", "--numstat", "-z", "-M", f"{base}...{head}"], cwd=cwd, capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return parse_numstat_z(proc.stdout)


def analyze(changes: list[FileChange], ignores=DEFAULT_IGNORES, limits=DEFAULT_LIMITS) -> SizeReport:
    report = SizeReport()
    for c in changes:
        (report.ignored if is_ignored(c.path, ignores) else report.counted).append(c)
    report.label = label_for(report.lines, limits)
    return report


def render(report: SizeReport) -> str:
    lines = [f"size/{report.label}: {report.lines} changed lines in {len(report.counted)} files"
             f" ({len(report.ignored)} ignored: lock files, generated, snapshots)"]
    if report.counted:
        lines += ["", "| Area | Files | Lines |", "|---|---:|---:|"]
        lines += [f"| {a} | {n} | {l} |" for a, n, l in report.by_area()]
    binaries = [f.path for f in report.counted if f.binary]
    if binaries:
        lines += ["", "Binary files (not counted as lines): " + ", ".join(binaries)]
    if report.label in ("L", "XL"):
        top = report.by_area()
        hint = ", ".join(f"{a} ({l})" for a, _, l in top[:3])
        lines += ["", f"Consider splitting along these areas: {hint}."]
    return "\n".join(lines)
