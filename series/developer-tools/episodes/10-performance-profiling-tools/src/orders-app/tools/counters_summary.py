#!/usr/bin/env python3
"""Summarize a `dotnet-counters collect --format json` file taken with --counters System.Runtime,Microsoft.AspNetCore.Hosting.

Rates (allocated bytes, GC pause, CPU seconds, collections) are exported per refresh interval (1 s by default),
so their sum over the file is the total for the window. Request duration comes with percentile tags per route.

    python3 tools/counters_summary.py counters.json
    python3 tools/counters_summary.py counters.json --route /reports/monthly --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime


def tag_dict(tags: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in tags.split(",") if "=" in part)


def summarize(doc: dict, route: str = "/reports/monthly") -> dict:
    events = doc["Events"]
    rate_sum: dict[tuple[str, str], float] = defaultdict(float)
    working_set = 0.0
    p50: list[float] = []
    p95: list[float] = []
    first = last = None
    for e in events:
        name = e["name"].split(" (")[0]
        tags = tag_dict(e.get("tags", ""))
        moment = datetime.fromisoformat(e["timestamp"])
        first = moment if first is None else min(first, moment)
        last = moment if last is None else max(last, moment)
        if e["provider"] == "System.Runtime":
            if name == "dotnet.process.memory.working_set":
                working_set = max(working_set, e["value"])
            elif e["counterType"] == "Rate":
                rate_sum[(name, tags.get("gc.heap.generation") or tags.get("cpu.mode", ""))] += e["value"]
        elif name == "http.server.request.duration" and tags.get("http.route") == route and tags.get("http.request.method") == "GET":
            if tags.get("Percentile") == "50":
                p50.append(e["value"])
            elif tags.get("Percentile") == "95":
                p95.append(e["value"])
    seconds = max(1, round((last - first).total_seconds())) if first else 0
    allocated = rate_sum[("dotnet.gc.heap.total_allocated", "")]
    return {
        "seconds": seconds,
        "allocated_mb": round(allocated / 1_048_576, 1),
        "alloc_mb_per_s": round(allocated / 1_048_576 / max(1, seconds), 1),
        "gc_pause_s": round(rate_sum[("dotnet.gc.pause.time", "")], 2),
        "gen0": int(rate_sum[("dotnet.gc.collections", "gen0")]),
        "gen1": int(rate_sum[("dotnet.gc.collections", "gen1")]),
        "gen2": int(rate_sum[("dotnet.gc.collections", "gen2")]),
        "cpu_s": round(rate_sum[("dotnet.process.cpu.time", "user")] + rate_sum[("dotnet.process.cpu.time", "system")], 1),
        "working_set_mb": round(working_set / 1_048_576),
        "route": route,
        "request_p50_ms": round(1000 * sum(p50) / len(p50)) if p50 else None,
        "request_p95_ms": round(1000 * max(p95)) if p95 else None,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Summary of a dotnet-counters JSON export")
    parser.add_argument("file")
    parser.add_argument("--route", default="/reports/monthly")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])
    with open(args.file, encoding="utf-8") as handle:
        doc = json.load(handle)
    if not doc.get("Events"):
        print("no events in this file", file=sys.stderr)
        return 1
    s = summarize(doc, args.route)
    if args.json:
        print(json.dumps(s))
        return 0
    print(f"window {s['seconds']} s: CPU {s['cpu_s']} s, allocated {s['allocated_mb']} MB ({s['alloc_mb_per_s']} MB/s), "
          f"GC pause {s['gc_pause_s']} s, collections gen0/gen1/gen2 {s['gen0']}/{s['gen1']}/{s['gen2']}, working set max {s['working_set_mb']} MB")
    if s["request_p50_ms"] is None:
        print(f"GET {s['route']}: no request duration samples")
    else:
        print(f"GET {s['route']}: server-side p50 about {s['request_p50_ms']} ms, worst p95 {s['request_p95_ms']} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
