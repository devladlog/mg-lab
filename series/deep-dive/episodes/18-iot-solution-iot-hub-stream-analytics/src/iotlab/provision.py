"""Create device identities with the Azure CLI (az iot extension) and keep their connection strings in a local file.

Needs a signed-in `az` and a hub: runs in the lab, not in the unit tests (they only check the commands).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

HUB_NAME = re.compile(r"^[A-Za-z0-9-]{3,50}$")  # Learn: 3-50 alphanumeric characters and dash
LOCAL_FILE = "devices.local.json"  # never committed (.gitignore)

Runner = Callable[[Sequence[str]], str]


def az_runner(args: Sequence[str]) -> str:
    done = subprocess.run(["az", *args], check=True, capture_output=True, text=True)
    return done.stdout.strip()


def create_command(hub: str, device_id: str) -> list[str]:
    _check_hub(hub)
    return ["iot", "hub", "device-identity", "create", "--hub-name", hub, "--device-id", device_id, "--output", "none"]


def connection_string_command(hub: str, device_id: str) -> list[str]:
    _check_hub(hub)
    return ["iot", "hub", "device-identity", "connection-string", "show", "--hub-name", hub,
            "--device-id", device_id, "--query", "connectionString", "--output", "tsv"]


def _check_hub(hub: str) -> None:
    if not HUB_NAME.match(hub):
        raise ValueError(f"invalid IoT hub name {hub!r}")


def provision(hub: str, device_ids: Sequence[str], target: Path, run: Runner = az_runner) -> dict[str, str]:
    """Idempotent enough for a lab: a second `create` fails with 'already exists', so list first."""
    existing = set(json.loads(run(["iot", "hub", "device-identity", "list", "--hub-name", hub, "--query", "[].deviceId", "--output", "json"]) or "[]"))
    strings: dict[str, str] = {}
    for device_id in device_ids:
        if device_id not in existing:
            run(create_command(hub, device_id))
        strings[device_id] = run(connection_string_command(hub, device_id))
    write_private(target, strings)
    return strings


def write_private(target: Path, strings: dict[str, str]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(strings, handle, indent=2)
