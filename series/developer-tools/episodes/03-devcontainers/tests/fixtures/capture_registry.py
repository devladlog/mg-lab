#!/usr/bin/env python3
"""Re-record tests/fixtures/registry.json from the live registry (MCR). Run by hand; tests never call it.

Configs are trimmed to the fields the checker reads (created, Labels, Env) to keep the fixture small.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "orders-app" / "tools"))
import devcontainer_check as dc  # noqa: E402

TAGS = ["1-10.0-noble", "3-10.0-noble", "10.0-noble"]
recorded: dict[str, str] = {}


def recording_fetch(url, accept):
    status, headers, body = dc.http_fetch(url, accept)
    if status == 200 and "/blobs/" in url:
        cfg = json.loads(body)
        keep = {"created": cfg.get("created"),
                "config": {k: cfg["config"].get(k) for k in ("Labels", "Env", "User")}}
        body = json.dumps(keep).encode()
    if status == 200:
        recorded[url] = body.decode()
    return status, headers, body


reg = dc.Registry(fetch=recording_fetch)
for tag in TAGS:
    reg.image_info(dc.ImageRef("mcr.microsoft.com", "devcontainers/dotnet", tag))
out = Path(__file__).with_name("registry.json")
out.write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n")
print(f"recorded {len(recorded)} responses -> {out}")
