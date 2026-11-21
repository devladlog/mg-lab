#!/usr/bin/env python3
"""Static checks for a Postman collection and its environments, before anything runs.

    python3 tools/collection_lint.py orders-api.postman_collection.json environments/*.postman_environment.json

Rules (each one is a mistake that still gives a green Newman run):
  no-tests       a request has no pm.test() of its own (collection-level tests don't count: they only prove speed)
  no-status      a request never asserts its status code
  hardcoded-host a URL doesn't start with {{baseUrl}}, so it can't be pointed at another environment
  secret         a Bearer token / API key literal in a request, or a secret-looking environment variable that
                 isn't type "secret" or has a value (exports must never carry credentials)
  duplicate      two requests with the same name in one folder (Postman and the reports can't tell them apart)
Exit 1 when any rule fires. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

SECRET_NAME = re.compile(r"(secret|token|password|passwd|api[_-]?key|client[_-]?secret)", re.I)
SECRET_VALUE = re.compile(r"(Bearer\s+[A-Za-z0-9._~+/=-]{16,}|PMAK-[A-Za-z0-9-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
STATUS = re.compile(r"to\.have\.status\(|pm\.response\.code|\.to\.be\.oneOf\(\[\d{3}")


def _requests(items, trail=()):
    seen = {}
    for it in items:
        if "item" in it:
            yield from _requests(it["item"], trail + (it["name"],))
        else:
            seen[it["name"]] = seen.get(it["name"], 0) + 1
            yield " / ".join(trail + (it["name"],)), it, seen[it["name"]] > 1


def _own_test_code(item) -> str:
    return "\n".join(l for e in item.get("event", []) if e["listen"] == "test" for l in e["script"]["exec"])


def lint_collection(col: dict) -> list[str]:
    problems = []
    for name, it, dup in _requests(col.get("item", [])):
        req = it["request"]
        code = _own_test_code(it)
        if "pm.test(" not in code:
            problems.append(f"no-tests: '{name}' has no pm.test()")
        elif not STATUS.search(code):
            problems.append(f"no-status: '{name}' never asserts the status code")
        url = req["url"]["raw"] if isinstance(req["url"], dict) else req["url"]
        if not url.startswith("{{baseUrl}}"):
            problems.append(f"hardcoded-host: '{name}' calls {url}")
        blob = json.dumps(req)
        if SECRET_VALUE.search(blob):
            problems.append(f"secret: '{name}' contains a credential literal")
        if dup:
            problems.append(f"duplicate: '{name}' appears twice in its folder")
    for v in col.get("variable", []):
        if SECRET_NAME.search(v.get("key", "")) and v.get("value"):
            problems.append(f"secret: collection variable '{v['key']}' looks like a secret and has a value")
    return problems


def lint_environment(env: dict, label: str = "environment") -> list[str]:
    problems = []
    for v in env.get("values", []):
        key = v.get("key", "")
        if SECRET_NAME.search(key) and (v.get("type") != "secret" or v.get("value")):
            problems.append(f"secret: {label} variable '{key}' must be type \"secret\" with an empty value in Git")
        if isinstance(v.get("value"), str) and SECRET_VALUE.search(v["value"]):
            problems.append(f"secret: {label} variable '{key}' holds a credential literal")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("collection")
    ap.add_argument("environments", nargs="*")
    a = ap.parse_args(argv)
    with open(a.collection, encoding="utf-8") as f:
        col = json.load(f)
    problems = lint_collection(col)
    for path in a.environments:
        with open(path, encoding="utf-8") as f:
            problems += lint_environment(json.load(f), path)
    n = sum(1 for _ in _requests(col.get("item", [])))
    for p in problems:
        print(f"✗ {p}")
    if not problems:
        print(f"✓ {n} requests, {len(a.environments)} environment(s): no problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
