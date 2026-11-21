#!/usr/bin/env python3
"""Which operations in the OpenAPI document does the Postman collection actually test?

    python3 tools/openapi_coverage.py openapi.v1.json orders-api.postman_collection.json

An operation is covered when some request has the same method and a path that fits the template
(`/orders/{id}` fits `/orders/{{orderId}}`, `/orders/abc` and `/orders/:id`). A documented response is
covered when a covering request asserts that status code (`to.have.status(404)`). Exit 1 when an operation
has no request, a documented status is never asserted, or a request matches nothing in the document
(a renamed or removed endpoint the collection still calls). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
STATUS_RE = re.compile(r"to\.have\.status\((\d{3})\)")


def operations(spec: dict) -> dict[tuple[str, str], set[str]]:
    """(METHOD, path template) -> documented status codes."""
    ops = {}
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method in METHODS:
                ops[(method.upper(), path)] = {c for c in op.get("responses", {}) if c.isdigit()}
    return ops


def _walk(items, trail=()):
    for it in items:
        if "item" in it:
            yield from _walk(it["item"], trail + (it["name"],))
        else:
            yield trail, it


def requests(collection: dict) -> list[dict]:
    out = []
    for trail, it in _walk(collection.get("item", [])):
        r = it["request"]
        url = r["url"]["raw"] if isinstance(r["url"], dict) else r["url"]
        path = re.sub(r"^\{\{\w+\}\}", "", url).split("?")[0]      # drop {{baseUrl}} and the query string
        code = "\n".join(
            line for e in it.get("event", []) if e["listen"] == "test" for line in e["script"]["exec"])
        out.append({"name": " / ".join(trail + (it["name"],)), "method": r["method"].upper(), "path": path,
                    "statuses": set(STATUS_RE.findall(code))})
    return out


def fits(template: str, path: str) -> bool:
    t, p = template.strip("/").split("/"), path.strip("/").split("/")
    return len(t) == len(p) and all(
        (ts.startswith("{") and ts.endswith("}")) or ts == ps for ts, ps in zip(t, p))


def check(spec: dict, collection: dict) -> tuple[list[str], list[str]]:
    """Returns (report lines, problems)."""
    ops, reqs = operations(spec), requests(collection)
    lines, problems, used = [], [], set()
    for (method, path), documented in sorted(ops.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mine = [r for r in reqs if r["method"] == method and fits(path, r["path"])]
        used.update(r["name"] for r in mine)
        asserted = set().union(*(r["statuses"] for r in mine)) if mine else set()
        missing = sorted(documented - asserted)
        mark = "ok " if mine and not missing else "!! "
        lines.append(f"{mark}{method:<5} {path:<14} requests: {len(mine)}  documented: {','.join(sorted(documented)) or '-'}"
                     f"  asserted: {','.join(sorted(asserted)) or '-'}")
        if not mine:
            problems.append(f"{method} {path} has no request in the collection")
        elif missing:
            problems.append(f"{method} {path}: documented but never asserted: {', '.join(missing)}")
    for r in reqs:
        if r["name"] not in used:
            problems.append(f"request '{r['name']}' ({r['method']} {r['path']}) matches no operation in the OpenAPI document")
    return lines, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("openapi")
    ap.add_argument("collection")
    a = ap.parse_args(argv)
    with open(a.openapi, encoding="utf-8") as f, open(a.collection, encoding="utf-8") as g:
        lines, problems = check(json.load(f), json.load(g))
    print("\n".join(lines))
    for p in problems:
        print(f"✗ {p}")
    if not problems:
        print(f"✓ {len(lines)} operations, all covered")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
