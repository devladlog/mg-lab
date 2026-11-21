#!/usr/bin/env python3
"""Sends POST /quotes from N worker threads for S seconds and prints what came back.

Container Apps' HTTP scale rule divides the requests of the last 15 seconds by 15 and compares the result with
`concurrentRequests` (20 in aca.bicep), so ~60 requests/second already asks for 3 replicas.
Standard library only.   Usage: infra/load.py <base-url> [workers=24] [seconds=90]
"""
import collections
import json
import sys
import threading
import time
import urllib.error
import urllib.request

BODY = json.dumps({"lines": [{"sku": "MON-270", "quantity": 2}, {"sku": "DOC-100", "quantity": 1}]}).encode()


def run(base_url: str, workers: int = 24, seconds: float = 90) -> dict:
    deadline = time.monotonic() + seconds
    counts: collections.Counter = collections.Counter()
    lock = threading.Lock()

    def worker() -> None:
        local: collections.Counter = collections.Counter()
        req = urllib.request.Request(base_url.rstrip("/") + "/quotes", data=BODY, method="POST",
                                     headers={"Content-Type": "application/json"})
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    local[r.status] += 1
            except urllib.error.HTTPError as e:
                local[e.code] += 1
            except OSError:
                local["error"] += 1
        with lock:
            counts.update(local)

    started = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started
    total = sum(counts.values())
    return {"total": total, "seconds": round(elapsed, 1), "per_second": round(total / elapsed, 1),
            "status": {str(k): v for k, v in sorted(counts.items(), key=lambda kv: str(kv[0]))}}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 24,
                         float(sys.argv[3]) if len(sys.argv) > 3 else 90)))
