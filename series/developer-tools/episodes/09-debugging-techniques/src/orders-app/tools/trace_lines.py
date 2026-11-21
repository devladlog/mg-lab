#!/usr/bin/env python3
"""Print the log lines that belong to one request.

The API logs JSON (Logging__Console__FormatterName=json, FormatterOptions__IncludeScopes=true); every line carries
the request's TraceId in its scopes. A caller who got a problem details body sends you its "traceId" field, which is
the W3C form "00-<trace id>-<span id>-<flags>"; the logs hold the bare 32 characters. This takes either form.

    docker logs orders-api 2>&1 | python3 tools/trace_lines.py 00-4bf92f3577b34da6a3ce929d0e0e4736-0abc5f20fe987725-01
    python3 tools/trace_lines.py 4bf92f3577b34da6a3ce929d0e0e4736 < api.log
"""
from __future__ import annotations

import json
import re
import sys

W3C = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")
BARE = re.compile(r"^[0-9a-f]{32}$")


def trace_id(text: str) -> str:
    """The bare 32-character trace id from either form; ValueError for anything else."""
    text = text.strip().lower()
    if m := W3C.match(text):
        return m.group(1)
    if BARE.match(text):
        return text
    raise ValueError(f"not a trace id: {text!r} (expected 32 hex characters or 00-<32 hex>-<16 hex>-<2 hex>)")


def lines_for(trace: str, lines):
    """Yield (level, category, message) for every JSON log line whose scopes contain this TraceId."""
    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue                       # the host also prints plain text lines (unhandled exceptions, dotnet run banners)
        if not isinstance(entry, dict):
            continue
        scopes = entry.get("Scopes") or []
        if any(isinstance(s, dict) and s.get("TraceId") == trace for s in scopes):
            yield entry.get("LogLevel", "?"), entry.get("Category", "?"), entry.get("Message", "")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        trace = trace_id(argv[1])
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    found = 0
    for level, category, message in lines_for(trace, sys.stdin):
        print(f"{level:<11} {category}: {message}")
        found += 1
    if not found:
        print(f"no log line with TraceId {trace}", file=sys.stderr)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
