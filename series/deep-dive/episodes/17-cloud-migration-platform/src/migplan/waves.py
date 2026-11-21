"""Group servers into migration waves from their network dependencies.

Rules (ours, written down so the tests can pin them):
1. Shared services (domain controllers, DNS, monitoring) are not grouped by dependency: everything talks to them.
   They form the foundation step, handled before wave 1 (extend or replicate identity to Azure first).
2. Application ports only: infrastructure ports (DNS, Kerberos, SMB, RPC, remoting) do not create edges.
3. Servers connected by an application port stay in the same wave (a connected component), so an app and its database move together.
4. Wave 1 is the pilot: the lowest-criticality group, smallest first. Later waves: criticality ascending, then size.
5. A group bigger than `max_wave_size` is reported, not split silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .inventory import Inventory, dependency_edges
from .readiness import Finding

CRITICALITY = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Wave:
    number: int
    name: str
    servers: list[str]
    criticality: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Plan:
    foundation: list[str]
    waves: list[Wave]
    blocked: list[str]
    warnings: list[str]


def _components(names: list[str], edges: set[frozenset[str]]) -> list[list[str]]:
    parent = {n: n for n in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for edge in edges:
        a, b = sorted(edge)
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(find(name), []).append(name)
    return [sorted(g) for g in groups.values()]


def plan_waves(inv: Inventory, findings: list[Finding] | None = None, max_wave_size: int = 8) -> Plan:
    findings = findings or []
    blocked = sorted({f.server for f in findings if f.severity == "blocker"})
    by_name = {s.name: s for s in inv.servers}
    foundation = sorted(s.name for s in inv.servers if s.shared_service)
    movable = [s.name for s in inv.servers if not s.shared_service and s.name not in blocked]
    edges = dependency_edges(inv)
    warnings: list[str] = []

    # An edge to a blocked server pulls its partners along: say so instead of moving half an application.
    for edge in edges:
        a, b = sorted(edge)
        if (a in blocked) != (b in blocked) and not (by_name[a].shared_service or by_name[b].shared_service):
            warnings.append(f"{a} and {b} depend on each other but only one is ready: they cannot move in the same wave until the blocker is fixed")

    groups = _components(movable, edges)

    def crit(group: list[str]) -> int:
        return max(CRITICALITY.get(by_name[n].criticality, 1) for n in group)

    groups.sort(key=lambda g: (crit(g), len(g), g[0]))
    waves = []
    for number, group in enumerate(groups, start=1):
        level = {v: k for k, v in CRITICALITY.items()}[crit(group)]
        wave = Wave(number, "pilot" if number == 1 else f"wave {number}", group, level)
        if len(group) > max_wave_size:
            wave.notes.append(f"{len(group)} servers depend on each other: more than {max_wave_size}, review the dependencies before cutting it")
        waves.append(wave)
    return Plan(foundation, waves, blocked, warnings)
