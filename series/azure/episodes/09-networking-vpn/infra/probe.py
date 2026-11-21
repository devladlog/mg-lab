#!/usr/bin/env python3
"""Reachability probe for the private orders service, run from the laptop while the VPN is connected.

  probe.py 10.61.0.4                 -> TCP connect + GET /, prints one JSON line, exit 0 when reachable
  probe.py 10.61.0.4 --expect closed -> exit 0 only when the service is NOT reachable (VPN disconnected)

The service answers with the address it sees the request coming from ("client"): that is the VPN client pool address.
Stdlib only.
"""
from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
import time


def probe(host: str, port: int, path: str, timeout: float) -> dict:
    result: dict = {"target": f"{host}:{port}", "reachable": False}
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result["tcp_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except OSError as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        result["status"] = resp.status
        try:
            result["body"] = json.loads(body)
        except ValueError:
            result["body"] = body[:200]
        result["reachable"] = resp.status == 200
    except (OSError, http.client.HTTPException) as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--path", default="/")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--expect", choices=["open", "closed"], default="open")
    args = ap.parse_args(argv)
    result = probe(args.host, args.port, args.path, args.timeout)
    print(json.dumps(result))
    return 0 if result["reachable"] == (args.expect == "open") else 1


if __name__ == "__main__":
    sys.exit(main())
