#!/usr/bin/env python3
"""A small, repeatable load for the monthly revenue report.

Every round: POST /reports/cache/invalidate (the report is cached per month, a cached answer measures nothing), then
GET /reports/monthly?month=2026-MM for the next month in the list, timed. Workers run in parallel threads.
Prints requests, errors, p50, p95 and max latency in milliseconds; exits 1 when any request failed.

    python3 tools/load.py http://localhost:8080 --seconds 20 --workers 2
    python3 tools/load.py http://localhost:8080 --requests 30 --json     # a fixed number of requests, machine-readable
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
import urllib.error
import urllib.request

MONTHS = [f"2026-{m:02d}" for m in range(1, 11)]       # the seed data covers 2026-01-01 .. 2026-10-27


def percentile(sorted_ms: list[float], p: float) -> float:
    """Nearest-rank percentile of an already sorted list (p in 0..100); 0.0 for an empty list."""
    if not sorted_ms:
        return 0.0
    rank = max(1, math.ceil(p / 100 * len(sorted_ms)))
    return sorted_ms[rank - 1]


def summarize(latencies_ms: list[float], errors: int) -> dict:
    ordered = sorted(latencies_ms)
    return {"requests": len(ordered) + errors, "errors": errors,
            "p50_ms": round(percentile(ordered, 50), 1), "p95_ms": round(percentile(ordered, 95), 1),
            "max_ms": round(ordered[-1], 1) if ordered else 0.0}


def one_round(base: str, month: str, timeout: float) -> float:
    """Invalidate the cache, then time one report request. Returns milliseconds; raises OSError or HTTPError on failure."""
    urllib.request.urlopen(urllib.request.Request(f"{base}/reports/cache/invalidate", method="POST", data=b""), timeout=timeout).close()
    started = time.perf_counter()
    with urllib.request.urlopen(f"{base}/reports/monthly?month={month}", timeout=timeout) as response:
        response.read()
    return (time.perf_counter() - started) * 1000


def run(base: str, workers: int, seconds: float | None, requests: int | None, timeout: float = 60.0) -> dict:
    base = base.rstrip("/")
    latencies: list[float] = []
    errors = [0]
    lock = threading.Lock()
    counter = [0]
    deadline = time.time() + seconds if seconds else None

    def worker(index: int) -> None:
        while True:
            with lock:
                if requests is not None and counter[0] >= requests:
                    return
                if deadline is not None and time.time() >= deadline:
                    return
                n = counter[0]
                counter[0] += 1
            month = MONTHS[(n + index) % len(MONTHS)]
            try:
                ms = one_round(base, month, timeout)
            except (OSError, urllib.error.URLError):
                with lock:
                    errors[0] += 1
                continue
            with lock:
                latencies.append(ms)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return summarize(latencies, errors[0])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Load for GET /reports/monthly (the cache is emptied before every request)")
    parser.add_argument("base_url")
    parser.add_argument("--workers", type=int, default=2)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--seconds", type=float, help="run this long (default 20 when --requests is not given)")
    group.add_argument("--requests", type=int, help="stop after this many requests in total")
    parser.add_argument("--json", action="store_true", help="print the summary as one JSON object")
    args = parser.parse_args(argv[1:])
    seconds = args.seconds if args.seconds is not None else (None if args.requests else 20.0)
    result = run(args.base_url, args.workers, seconds, args.requests)
    if args.json:
        print(json.dumps(result))
    else:
        print(f"{result['requests']} requests, {result['errors']} errors, "
              f"p50 {result['p50_ms']} ms, p95 {result['p95_ms']} ms, max {result['max_ms']} ms")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
