"""python -m azmcp_audit catalog | report | config | probe"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog, policy as pol, probe


def _load(args) -> list[catalog.Tool]:
    if args.catalog:
        return catalog.load_catalog(args.catalog)
    return catalog.parse_catalog(catalog.run_tools_list(args.azmcp))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="azmcp_audit", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalog", help="save `azmcp tools list` to a file")
    c.add_argument("--azmcp", default="azmcp")
    c.add_argument("--out", type=Path, required=True)

    for name, help_ in (("report", "what a policy exposes, and which exposed tools carry a risk annotation"),
                        ("config", "print the .vscode/mcp.json for a policy")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("policy", type=Path)
        s.add_argument("--catalog", type=Path, help="catalog JSON; default: run `azmcp tools list`")
        s.add_argument("--azmcp", default="azmcp")
        if name == "report":
            s.add_argument("--fail-on-findings", action="store_true")

    pr = sub.add_parser("probe", help="start the real server with the policy's arguments and compare")
    pr.add_argument("policy", type=Path)
    pr.add_argument("--catalog", type=Path)
    pr.add_argument("--azmcp", default="azmcp")
    pr.add_argument("--call", help="also call this tool (needs an Azure sign-in), e.g. group_list")
    pr.add_argument("--arguments", default="{}", help="JSON arguments for --call")

    a = p.parse_args(argv)

    if a.cmd == "catalog":
        text = catalog.run_tools_list(a.azmcp)
        a.out.write_text(text, encoding="utf-8")
        print(f"Saved {len(catalog.parse_catalog(text))} tools to {a.out}")
        return 0

    policy = pol.Policy.load(a.policy)
    tools = _load(a)

    if a.cmd == "config":
        print(json.dumps(pol.vscode_mcp_json(policy), indent=2))
        return 0

    missing = pol.unknown_namespaces(tools, policy)
    if missing:
        print(f"[ERROR] unknown namespace(s) in the policy: {', '.join(missing)}")
        return 2

    if a.cmd == "report":
        print(f"Policy {policy.name}: {len(policy.namespaces)} namespace(s), read-only={policy.read_only}")
        print(f"{'namespace':<16}{'tools':>6}{'readonly':>9}{'writes':>7}{'destructive':>12}{'secret':>7}{'exposed':>8}")
        for r in pol.namespace_report(tools, policy):
            print(f"{r['namespace']:<16}{r['tools']:>6}{r['read_only']:>9}{r['writes']:>7}{r['destructive']:>12}"
                  f"{r['secret']:>7}{r['exposed']:>8}")
        exposed = pol.expected_tools(tools, policy)
        print(f"Exposed with `azmcp server start {' '.join(pol.start_args(policy)[2:])}`: {len(exposed)} tool(s)")
        found = pol.findings(tools, policy)
        for risk, t in found:
            print(f"  [RISK:{risk}] {t.name}")
        print(f"Findings: {len(found)}")
        return 1 if (found and a.fail_on_findings) else 0

    # probe
    args = pol.start_args(policy, "all") + ["--disable-proxy-tools"]
    info, listed = probe.list_server_tools(a.azmcp, args)
    got = sorted(t["name"] for t in listed)
    want = [t.name for t in pol.expected_tools(tools, policy)]
    print(f"Server: {info['serverInfo']['name']} {info['serverInfo']['version']}  (start line: azmcp {' '.join(args)})")
    print(f"Published {len(got)} tool(s); the catalog predicts {len(want)}")
    only_server, only_catalog = sorted(set(got) - set(want)), sorted(set(want) - set(got))
    for n in only_server:
        print(f"  [SERVER ONLY] {n}")
    for n in only_catalog:
        print(f"  [CATALOG ONLY] {n}")
    ro_hint = {t["name"]: t.get("annotations", {}).get("readOnlyHint") for t in listed}
    if policy.read_only and not all(ro_hint.values()):
        print("  [WARN] --read-only is on but some published tools do not carry readOnlyHint=true")
    ok = not only_server and not only_catalog
    print("Match: yes" if ok else "Match: NO")
    # the mode the generated mcp.json uses: the commands behind the namespace tools must be the same set
    published, commands = probe.namespace_surface(a.azmcp, pol.start_args(policy, "namespace"))
    same = commands == set(want)
    print(f"Namespace mode (what mcp.json starts): {len(published)} tool(s) publish {len(commands)} command(s): "
          f"{'same set' if same else 'DIFFERENT SET'}")
    ok = ok and same
    if a.call:
        result = probe.call_server_tool(a.azmcp, args, a.call, json.loads(a.arguments))
        print(json.dumps(result, indent=2)[:4000])
    return 0 if ok else 1
