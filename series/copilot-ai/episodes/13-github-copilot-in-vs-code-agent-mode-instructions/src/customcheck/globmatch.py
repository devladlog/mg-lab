"""Match `applyTo` patterns the way the VS Code reference table describes them.

Patterns are relative to the workspace root and use `/`. `*` does not cross a folder, `**`
crosses any number of folders (including none), several patterns are comma separated.
This is an offline approximation of the documented table, not VS Code's own matcher.
"""
from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def split_patterns(apply_to: str) -> list[str]:
    return [p.strip() for p in apply_to.split(",") if p.strip()]


def matches(apply_to: str, relpath: str) -> bool:
    relpath = relpath.replace("\\", "/")
    if relpath.startswith("./"):
        relpath = relpath[2:]
    return any(_compile(p).match(relpath) for p in split_patterns(apply_to))
