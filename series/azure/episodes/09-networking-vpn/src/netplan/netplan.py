#!/usr/bin/env python3
"""Address plan checker for the contoso hub-and-spoke network (DEVLADLOG Azure #9).

Stdlib only. Two commands:
  netplan.py check  plan.json   -> findings, exit 1 on any error
  netplan.py params plan.json   -> ARM deployment parameters for infra/main.bicep (JSON on stdout)

Rules come from Microsoft Learn: no overlapping address spaces between networks that peer or connect over a gateway,
5 reserved addresses per subnet, GatewaySubnet /27 or larger, AzureFirewallSubnet and AzureBastionSubnet /26 or larger.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from dataclasses import dataclass

RESERVED_PER_SUBNET = 5
SMALLEST_SUBNET_PREFIXLEN = 29
# Required name -> longest allowed prefix length (smallest allowed size) for platform subnets.
DEDICATED_SUBNETS = {"GatewaySubnet": 27, "AzureFirewallSubnet": 26, "AzureBastionSubnet": 26}
# The first usable address Azure hands out in a subnet is .4 (.0 network, .1 gateway, .2 and .3 DNS).
FIRST_HOST_OFFSET = 4


@dataclass
class Finding:
    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.message}"


def net(text: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(text, strict=True)


def usable_addresses(prefix: str) -> int:
    """Addresses a workload can really use in a subnet: total minus the 5 Azure keeps."""
    return max(net(prefix).num_addresses - RESERVED_PER_SUBNET, 0)


def workload_vm_ip(prefix: str) -> str:
    """The deterministic first address Azure allows in a subnet (network address + 4)."""
    return str(net(prefix).network_address + FIRST_HOST_OFFSET)


def _parse(label: str, text: str, findings: list[Finding]) -> ipaddress.IPv4Network | None:
    try:
        n = net(text)
    except ValueError as e:
        findings.append(Finding("error", f"{label}: '{text}' is not a valid IPv4 CIDR ({e})"))
        return None
    if not n.is_private:
        findings.append(Finding("error", f"{label}: {n} is not a private range"))
    return n


def check(plan: dict) -> list[Finding]:
    findings: list[Finding] = []
    named: list[tuple[str, ipaddress.IPv4Network]] = []

    for site in plan.get("onPremises", []):
        n = _parse(f"on-premises '{site['name']}'", site["cidr"], findings)
        if n:
            named.append((f"on-premises '{site['name']}'", n))

    for role in ("hub", "spoke"):
        vnet = plan[role]
        n = _parse(f"{role} VNet '{vnet['name']}'", vnet["addressSpace"], findings)
        if n:
            named.append((f"{role} VNet '{vnet['name']}'", n))
        findings += _check_subnets(role, vnet, n)

    pool = _parse("point-to-site client pool", plan["p2sPool"], findings)
    if pool:
        named.append(("point-to-site client pool", pool))

    for i, (a_name, a) in enumerate(named):
        for b_name, b in named[i + 1:]:
            if a.overlaps(b):
                findings.append(Finding("error", f"{a_name} {a} overlaps {b_name} {b}: routing breaks without address translation"))

    hub_subnets = {s["name"] for s in plan["hub"]["subnets"]}
    if "GatewaySubnet" not in hub_subnets:
        findings.append(Finding("error", "hub VNet has no subnet named exactly 'GatewaySubnet' (required for a VPN gateway)"))
    return findings


def _check_subnets(role: str, vnet: dict, space: ipaddress.IPv4Network | None) -> list[Finding]:
    out: list[Finding] = []
    seen: list[tuple[str, ipaddress.IPv4Network]] = []
    for s in vnet["subnets"]:
        label = f"{role} subnet '{s['name']}'"
        n = _parse(label, s["prefix"], out)
        if n is None:
            continue
        if space and not n.subnet_of(space):
            out.append(Finding("error", f"{label} {n} is outside the VNet address space {space}"))
        if n.prefixlen > SMALLEST_SUBNET_PREFIXLEN:
            out.append(Finding("error", f"{label} {n} is smaller than /{SMALLEST_SUBNET_PREFIXLEN}, the smallest subnet Azure supports"))
        limit = DEDICATED_SUBNETS.get(s["name"])
        if limit and n.prefixlen > limit:
            out.append(Finding("error", f"{label} {n} is too small: {s['name']} needs /{limit} or larger"))
        for other_name, other in seen:
            if n.overlaps(other):
                out.append(Finding("error", f"{label} {n} overlaps subnet '{other_name}' {other}"))
        seen.append((s["name"], n))
    return out


def arm_parameters(plan: dict) -> dict:
    """Parameters for infra/main.bicep. Secrets (certificate data, SSH key) are added by deploy.sh, not stored here."""
    hub, spoke = plan["hub"], plan["spoke"]
    gateway = next(s for s in hub["subnets"] if s["name"] == "GatewaySubnet")
    workload = spoke["subnets"][0]
    values = {
        "hubAddressSpace": hub["addressSpace"],
        "gatewaySubnetPrefix": gateway["prefix"],
        "spokeAddressSpace": spoke["addressSpace"],
        "workloadSubnetPrefix": workload["prefix"],
        "workloadVmIp": workload_vm_ip(workload["prefix"]),
        "p2sPoolPrefix": plan["p2sPool"],
    }
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {k: {"value": v} for k, v in values.items()},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "params"])
    ap.add_argument("plan")
    args = ap.parse_args(argv)
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    findings = check(plan)
    errors = [f for f in findings if f.level == "error"]
    if args.command == "check":
        for f in findings:
            print(f)
        if not errors:
            sub = plan["spoke"]["subnets"][0]["prefix"]
            print(f"OK: no overlaps; workload subnet {sub} has {usable_addresses(sub)} usable addresses; VM gets {workload_vm_ip(sub)}")
        return 1 if errors else 0
    if errors:
        for f in errors:
            print(f, file=sys.stderr)
        return 1
    json.dump(arm_parameters(plan), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
