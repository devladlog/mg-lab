"""python -m vendor_api [--port 8080] [--host 127.0.0.1] [--today 2026-11-21]

The API key comes from the VENDOR_API_KEY environment variable (never from a file or an argument)."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from .app import serve


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vendor_api", description="Run the Contoso Vendor Renewals API (demo data).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--today", help="Pretend today is this date (YYYY-MM-DD), for repeatable recordings.")
    a = p.parse_args(argv)
    key = os.environ.get("VENDOR_API_KEY", "")
    if not key:
        print("Set VENDOR_API_KEY first (any long random string). The API does not run without a key.", file=sys.stderr)
        return 2
    fixed = date.fromisoformat(a.today) if a.today else None
    server = serve(key, a.host, a.port, (lambda: fixed) if fixed else date.today)
    print(f"Vendor Renewals API on http://{a.host}:{a.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
