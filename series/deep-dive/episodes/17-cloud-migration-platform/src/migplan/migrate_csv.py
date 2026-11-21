"""Write the Azure Migrate "Import using CSV" file. The header row is the one in Microsoft's template (data/import-template-headers.txt)."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .inventory import Server
from .readiness import MAX_DISKS

TEMPLATE = Path(__file__).resolve().parents[2] / "data" / "import-template-headers.txt"
DISK_COLUMNS = ("size (In GB)", "read throughput (MB per second)", "write throughput (MB per second)",
                "read ops (operations per second)", "write ops (operations per second)")


def template_headers() -> list[str]:
    return TEMPLATE.read_text(encoding="utf-8").strip().split(",")


def headers_for(max_disks: int) -> list[str]:
    """Template headers, plus the same five columns for every extra disk (Learn: add similar columns, up to 20 disks)."""
    base = template_headers()
    if max_disks > MAX_DISKS:
        raise ValueError(f"the import takes at most {MAX_DISKS} disks")
    present = max((int(h.split()[1]) for h in base if h.startswith("Disk ")), default=0)
    extra = [f"Disk {n} {col}" for n in range(present + 1, max_disks + 1) for col in DISK_COLUMNS]
    return base + extra


def _row(server: Server, headers: list[str]) -> dict[str, object]:
    row: dict[str, object] = {h: "" for h in headers}
    plain = {h.lstrip("*"): h for h in headers}

    def put(name: str, value: object) -> None:
        if value not in (None, ""):
            row[plain[name]] = value

    put("Server name", server.fqdn or server.name)
    put("IP addresses", ";".join(server.ips))
    put("Cores", server.cores)
    put("Memory (In MB)", server.memory_mb)
    put("OS name", server.os_name)
    put("OS version", server.os_version)
    put("OS architecture", server.os_arch)
    put("Server type", server.server_type)
    put("Hypervisor", server.hypervisor)
    put("CPU utilization percentage", server.cpu_util_pct)
    put("Memory utilization percentage", server.mem_util_pct)
    put("Boot type", server.boot_type)
    if server.disks_gb:
        put("Number of disks", len(server.disks_gb))
        for number, size in enumerate(server.disks_gb, start=1):
            put(f"Disk {number} size (In GB)", int(size) if float(size).is_integer() else size)
    return row


def render(servers: list[Server]) -> str:
    headers = headers_for(max((len(s.disks_gb) for s in servers), default=0))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    for server in servers:
        writer.writerow(_row(server, headers))
    return out.getvalue()


def write(servers: list[Server], path: Path) -> None:
    path.write_text(render(servers), encoding="utf-8-sig", newline="")  # the template itself starts with a BOM
