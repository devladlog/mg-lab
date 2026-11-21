"""Pre-flight checks on an inventory before it goes to Azure Migrate.

These are *our* checks on the data and the obvious blockers. Azure Migrate's assessment stays the authority on Azure readiness.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from .inventory import Inventory, Server

# Learn, "Tutorial: Build a business case or assess servers using an imported CSV file": the assessment recognises
# OS names that match or contain one of these strings.
SUPPORTED_OS_NAMES = (
    "Asianux 3", "Asianux 4", "Asianux 5", "CoreOS Linux", "Debian GNU/Linux 4", "Debian GNU/Linux 5", "Debian GNU/Linux 6",
    "Debian GNU/Linux 7", "Debian GNU/Linux 8", "FreeBSD", "IBM OS/2", "macOS X 10", "MS-DOS", "Novell NetWare 5", "Novell NetWare 6",
    "Oracle Linux", "Oracle Solaris 10", "Oracle Solaris 11", "Red Hat Enterprise Linux 2", "Red Hat Enterprise Linux 3",
    "Red Hat Enterprise Linux 4", "Red Hat Enterprise Linux 5", "Red Hat Enterprise Linux 6", "Red Hat Enterprise Linux 7",
    "Red Hat Enterprise Linux 8", "Red Hat Enterprise Linux 9", "Red Hat Fedora", "SCO OpenServer 5", "SCO OpenServer 6",
    "SCO UnixWare 7", "Serenity Systems eComStation", "Sun Microsystems Solaris 8", "Sun Microsystems Solaris 9",
    "SUSE Linux Enterprise 8/9", "SUSE Linux Enterprise 10", "SUSE Linux Enterprise 11", "SUSE Linux Enterprise 12", "SUSE openSUSE",
    "Ubuntu Linux", "VMware ESXi 4", "VMware ESXi 5", "VMware ESXi 6", "Windows 10", "Windows 2000", "Windows 3", "Windows 7",
    "Windows 8", "Windows 95", "Windows 98", "Windows NT", "Windows Server (R) 2008", "Windows Server 2003", "Windows Server 2008",
    "Windows Server 2008 R2", "Windows Server 2012", "Windows Server 2012 R2", "Windows Server 2016", "Windows Server 2019",
    "Windows Server 2022", "Windows Server 2025", "Windows Server Threshold", "Windows Vista", "Windows Web Server 2008 R2",
    "Windows XP Professional",
)
# Same page: "Windows Server 2008, 2008 R2, 2012 and 2012 R2 have reached End of Support".
END_OF_SUPPORT = re.compile(r"Windows Server (\(R\) )?(2008|2012)")
MAX_DISKS = 20  # "You can add details for ... up to twenty disks"
MAX_SERVERS_PER_PROJECT = 20_000  # same tutorial: up to 20,000 servers in one CSV and project


@dataclass(frozen=True)
class Finding:
    server: str
    severity: str  # blocker | warning | info
    code: str
    message: str


def check_server(server: Server, landing_zones: tuple[str, ...] = ()) -> list[Finding]:
    found: list[Finding] = []

    def add(severity: str, code: str, message: str) -> None:
        found.append(Finding(server.name, severity, code, message))

    for label, value in (("cores", server.cores), ("memoryMb", server.memory_mb), ("osName", server.os_name)):
        if value in (None, "", 0):
            add("blocker", "missing-field", f"{label} is required by the Azure Migrate CSV import")
    if server.os_name and not any(name in server.os_name for name in SUPPORTED_OS_NAMES):
        add("blocker", "os-name-not-recognised", f"'{server.os_name}' does not contain a name from the supported list, so it cannot be assessed")
    if server.os_name and END_OF_SUPPORT.search(server.os_name):
        add("warning", "os-end-of-support", "Learn lists this Windows Server version as end of support: plan an upgrade or the extended support option")
    if server.os_name and not server.os_version:
        add("info", "os-version-missing", "without OS version and architecture the Azure readiness verdict is less accurate (Learn)")
    if len(server.disks_gb) > MAX_DISKS:
        add("blocker", "too-many-disks", f"{len(server.disks_gb)} disks; the CSV takes up to {MAX_DISKS}")
    if not server.disks_gb:
        add("info", "no-disk-data", "no disk sizes: storage cannot be sized")
    for label, value in (("cpuUtilPct", server.cpu_util_pct), ("memUtilPct", server.mem_util_pct)):
        if value is not None and not 0 <= value <= 100:
            add("blocker", "utilisation-out-of-range", f"{label}={value} is not a percentage")
    if server.cpu_util_pct is None or server.mem_util_pct is None:
        add("info", "sized-as-is", "no utilisation: a performance-based assessment would size this server as-is (Learn)")
    for ip in server.ips:
        for cidr in landing_zones:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(cidr):
                add("blocker", "address-overlaps-landing-zone", f"{ip} is inside {cidr}: hybrid routing cannot tell the two apart")
    return found


def check_inventory(inv: Inventory, landing_zones: tuple[str, ...] = ()) -> list[Finding]:
    findings = [f for s in inv.servers for f in check_server(s, landing_zones)]
    if len(inv.servers) > MAX_SERVERS_PER_PROJECT:
        findings.append(Finding("*", "blocker", "too-many-servers", f"more than {MAX_SERVERS_PER_PROJECT} servers"))
    return findings


def importable(inv: Inventory, findings: list[Finding]) -> list[Server]:
    """Servers without a blocker."""
    blocked = {f.server for f in findings if f.severity == "blocker"}
    return [s for s in inv.servers if s.name not in blocked]
