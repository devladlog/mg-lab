#!/usr/bin/env python3
"""Smoke test for a running orders API: the same checks after `docker compose up` and after a deploy.

    python3 tools/smoke.py http://localhost:8080 --database SqlServer --version "$GITHUB_SHA"
    python3 tools/smoke.py https://<app>.azurewebsites.net --database Sqlite --version "$GITHUB_SHA" --read-only

A deploy isn't done when the platform says "succeeded", it's done when the app answers with the commit we
just built. /healthz is polled until it reports the expected version (or --timeout runs out), then the API
is exercised. Exit 0 = all checks passed, 1 = a check failed. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


class Http:
    def __init__(self, base: str, timeout: float = 10.0):
        self.base, self.timeout = base.rstrip("/"), timeout

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, dict(r.headers), _json(r.read())
        except urllib.error.HTTPError as e:            # 4xx/5xx still carry a body worth reading
            return e.code, dict(e.headers), _json(e.read())


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {"_raw": raw[:200].decode(errors="replace")}


def wait_for_version(http: Http, version: str | None, timeout: float, interval: float) -> tuple[bool, str]:
    """Poll /healthz until status is ok (and version matches). A restarting container gives errors for a while."""
    deadline, last = time.monotonic() + timeout, "no answer"
    while True:
        try:
            code, _, body = http.call("GET", "/healthz")
            last = f"HTTP {code} {body}"
            if code == 200 and body.get("status") == "ok" and (version is None or body.get("version") == version):
                return True, last
        except (urllib.error.URLError, OSError) as e:   # connection refused, reset, timeout
            last = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        if time.monotonic() >= deadline:
            return False, last
        time.sleep(interval)


def run(base: str, database: str | None, version: str | None, read_only: bool,
        timeout: float, interval: float) -> list[tuple[bool, str]]:
    http, results = Http(base), []

    def check(ok: bool, text: str) -> bool:
        results.append((bool(ok), text))
        return bool(ok)

    ok, last = wait_for_version(http, version, timeout, interval)
    if not check(ok, f"/healthz ok{f' and version {version}' if version else ''}" + ("" if ok else f" (last: {last})")):
        return results                                       # nothing else makes sense
    _, _, health = http.call("GET", "/healthz")
    if database:
        check(health.get("database") == database, f"database is {database} (got {health.get('database')})")

    code, _, page = http.call("GET", "/orders?page=1&pageSize=5")
    check(code == 200 and len(page.get("items", [])) == 5 and page.get("total", 0) >= 5,
          f"GET /orders?pageSize=5 returns 5 items (HTTP {code}, total {page.get('total')})")
    code, _, _ = http.call("GET", "/orders?page=0")
    check(code == 400, f"GET /orders?page=0 is a validation problem (HTTP {code})")

    if not read_only:
        code, headers, created = http.call("POST", "/orders", {"customer": "Alex Demo", "total": 19.99})
        location = headers.get("Location") or headers.get("location") or ""
        if check(code == 201 and location, f"POST /orders creates an order (HTTP {code}, Location {location or '-'})"):
            code, _, read = http.call("GET", location if location.startswith("/") else "/" + location.split("/", 3)[-1])
            check(code == 200 and read.get("customer") == "Alex Demo" and read.get("total") == 19.99,
                  f"GET {location} reads it back (HTTP {code})")
        code, _, problem = http.call("POST", "/orders", {"customer": "", "total": 0})
        check(code == 400 and {"customer", "total"} <= set(problem.get("errors", {})),
              f"invalid order is rejected with both field errors (HTTP {code})")
    return results


def report(base: str, results: list[tuple[bool, str]]) -> int:
    failed = [t for ok, t in results if not ok]
    lines = [f"{'✓' if ok else '✗'} {t}" for ok, t in results]
    print(f"Smoke test: {base}", *lines, f"{len(results) - len(failed)} passed, {len(failed)} failed", sep="\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:                                              # shows on the run page in GitHub Actions
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Smoke test: {base}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n\n")
    return 1 if failed or not results else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("base_url")
    p.add_argument("--database", help="expected /healthz database (Sqlite or SqlServer)")
    p.add_argument("--version", help="expected /healthz version (the commit SHA the image was built from)")
    p.add_argument("--read-only", action="store_true", help="no POSTs (use against production)")
    p.add_argument("--timeout", type=float, default=180, help="seconds to wait for /healthz (default 180)")
    p.add_argument("--interval", type=float, default=5, help="seconds between /healthz polls (default 5)")
    a = p.parse_args(argv)
    return report(a.base_url, run(a.base_url, a.database, a.version, a.read_only, a.timeout, a.interval))


if __name__ == "__main__":
    sys.exit(main())
