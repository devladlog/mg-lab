"""A first-guess Azure VM size per server, to compare with the real assessment. Not a replacement for it.

Learn (assessment calculation): as-is sizing looks at the allocated cores and memory; performance-based sizing multiplies the used
cores and memory by a comfort factor. Azure Migrate also looks at disks, IOPS and processor benchmarks: this module does not.
SKU specs are from the Dsv5 and Esv5 size pages on Learn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .inventory import Server


@dataclass(frozen=True)
class Sku:
    name: str
    vcpus: int
    memory_gib: int
    family: str


CATALOG = (
    Sku("Standard_D2s_v5", 2, 8, "D"), Sku("Standard_D4s_v5", 4, 16, "D"), Sku("Standard_D8s_v5", 8, 32, "D"),
    Sku("Standard_D16s_v5", 16, 64, "D"), Sku("Standard_D32s_v5", 32, 128, "D"),
    Sku("Standard_E2s_v5", 2, 16, "E"), Sku("Standard_E4s_v5", 4, 32, "E"), Sku("Standard_E8s_v5", 8, 64, "E"),
    Sku("Standard_E16s_v5", 16, 128, "E"), Sku("Standard_E32s_v5", 32, 256, "E"),
)


@dataclass(frozen=True)
class Recommendation:
    server: str
    mode: str  # as-is | performance
    need_cores: float
    need_memory_gib: float
    sku: Sku | None
    note: str = ""


def recommend(server: Server, comfort: float | None = None, performance: bool = True) -> Recommendation:
    """Smallest SKU (fewest vCPUs, then least memory) that covers the need: the D family unless memory forces the E family."""
    if not server.cores or not server.memory_mb:
        return Recommendation(server.name, "none", 0, 0, None, "cores and memory are required")
    cores, mem_gib = float(server.cores), server.memory_mb / 1024
    have_perf = performance and server.cpu_util_pct is not None and server.mem_util_pct is not None
    if have_perf:
        factor = 1.3 if comfort is None else comfort  # 1.3 is the example Learn uses; it is an assessment setting
        need_cores = cores * server.cpu_util_pct / 100 * factor
        need_mem = mem_gib * server.mem_util_pct / 100 * factor
        mode, note = "performance", f"comfort factor {factor}"
    else:
        factor = 1.0 if comfort is None else comfort
        need_cores, need_mem = cores * factor, mem_gib * factor
        mode, note = "as-is", "no utilisation data" if performance else "as-is requested"
    need_cores = max(need_cores, 1.0)  # a server never needs less than one core
    candidates = [s for s in CATALOG if s.vcpus >= math.ceil(need_cores - 1e-9) and s.memory_gib >= need_mem - 1e-9]
    if not candidates:
        return Recommendation(server.name, mode, need_cores, need_mem, None, "larger than the lab catalogue")
    return Recommendation(server.name, mode, round(need_cores, 2), round(need_mem, 2), min(candidates, key=lambda s: (s.vcpus, s.memory_gib)), note)
