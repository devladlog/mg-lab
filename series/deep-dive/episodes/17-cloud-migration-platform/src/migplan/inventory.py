"""Server inventory: what the PowerShell collector writes (or a CMDB export looks like)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Ports that nearly every server uses to reach shared infrastructure (DNS, Kerberos, time, RPC, LDAP, SMB, remoting).
# Dependency edges on these ports say "this is a domain member", not "these two servers belong together".
INFRA_PORTS = frozenset({53, 88, 123, 135, 389, 445, 464, 636, 3268, 3269, 3389, 5985, 5986})


@dataclass
class Server:
    name: str
    fqdn: str = ""
    ips: list[str] = field(default_factory=list)
    cores: int | None = None
    memory_mb: int | None = None
    os_name: str = ""
    os_version: str = ""
    os_arch: str = ""
    server_type: str = ""
    hypervisor: str = ""
    boot_type: str = ""
    disks_gb: list[float] = field(default_factory=list)
    cpu_util_pct: float | None = None
    mem_util_pct: float | None = None
    role: str = "unknown"          # web | app | database | shared-service | file | other
    criticality: str = "medium"    # low | medium | high

    @property
    def shared_service(self) -> bool:
        return self.role == "shared-service"


@dataclass
class Connection:
    source: str
    destination_ip: str
    port: int


@dataclass
class Inventory:
    servers: list[Server]
    connections: list[Connection]

    def by_name(self) -> dict[str, Server]:
        return {s.name.lower(): s for s in self.servers}

    def ip_index(self) -> dict[str, str]:
        return {ip: s.name for s in self.servers for ip in s.ips}


def _server(raw: dict) -> Server:
    return Server(
        name=raw["name"],
        fqdn=raw.get("fqdn", ""),
        ips=list(raw.get("ips", [])),
        cores=raw.get("cores"),
        memory_mb=raw.get("memoryMb"),
        os_name=raw.get("osName", ""),
        os_version=raw.get("osVersion", ""),
        os_arch=raw.get("osArch", ""),
        server_type=raw.get("serverType", ""),
        hypervisor=raw.get("hypervisor", ""),
        boot_type=raw.get("bootType", ""),
        disks_gb=[float(d) for d in raw.get("disksGb", [])],
        cpu_util_pct=raw.get("cpuUtilPct"),
        mem_util_pct=raw.get("memUtilPct"),
        role=raw.get("role", "unknown"),
        criticality=raw.get("criticality", "medium"),
    )


def load(path: Path | str) -> Inventory:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return from_dict(data)


def from_dict(data: dict) -> Inventory:
    servers = [_server(s) for s in data.get("servers", [])]
    names = [s.name.lower() for s in servers]
    if len(set(names)) != len(names):
        raise ValueError("duplicate server names in inventory (Azure Migrate keys imported servers by name)")
    conns = [Connection(c["source"], c["destinationIp"], int(c["port"])) for c in data.get("connections", [])]
    return Inventory(servers, conns)


def dependency_edges(inv: Inventory, ignore_ports: frozenset[int] = INFRA_PORTS) -> set[frozenset[str]]:
    """Undirected server pairs that talk on an application port. Unknown destinations (not in the inventory) are skipped."""
    ips = inv.ip_index()
    names = inv.by_name()
    edges: set[frozenset[str]] = set()
    for conn in inv.connections:
        if conn.port in ignore_ports:
            continue
        target = ips.get(conn.destination_ip)
        source = names.get(conn.source.lower())
        if target is None or source is None or source.name == target:
            continue
        edges.add(frozenset({source.name, target}))
    return edges
