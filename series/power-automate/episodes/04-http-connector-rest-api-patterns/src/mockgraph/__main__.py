"""python -m mockgraph [--port 8765] [--users samples/directory.json] [--throttle-page 2]

Runs the local Graph stand-in until Ctrl+C, for the CLI demo in README. Listens on 127.0.0.1 only.
"""
import argparse
import json
import time
from pathlib import Path

from .server import Fault, MockGraph


def main() -> int:
    p = argparse.ArgumentParser(prog="mockgraph")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--users", default=str(Path(__file__).resolve().parents[1] / "samples" / "directory.json"))
    p.add_argument("--throttle-page", type=int, help="answer this page once with 429 and Retry-After: 2")
    a = p.parse_args()
    users = json.loads(Path(a.users).read_text(encoding="utf-8"))
    faults = [Fault(429, page=a.throttle_page, retry_after=2)] if a.throttle_page else []
    with MockGraph(users, port=a.port, faults=faults) as g:
        print(f"mockgraph listening on {g.url} (tenant {g.state.tenant}, client {g.state.client_id}); Ctrl+C to stop",
              flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
