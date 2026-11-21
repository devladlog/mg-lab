"""A start-line policy: which namespaces to expose, read-only or not, and what is acceptable.

The server options come from the server itself (`azmcp server start --help`, 4.0.0-beta.9) and from Learn
("Azure MCP Server start parameters"): --namespace (repeatable), --read-only, --mode (namespace | consolidated | all |
single), --tool, --disable-proxy-tools. In --mode all with --namespace, the server publishes one MCP tool per command in
those namespaces, and with --read-only only the tools whose readOnly annotation is true: `expected_tools` predicts that,
and `probe.py` checks the prediction against the real server.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Tool

# Findings are raised for exposed tools carrying one of these annotations unless the policy allows it.
RISKS = ("destructive", "secret", "open_world")


@dataclass
class Policy:
    name: str
    namespaces: list[str]
    read_only: bool = True
    allow: list[str] = field(default_factory=list)   # risks the owner accepts, e.g. ["secret"]
    version: str = "4.0.0-beta.9"                    # pinned on purpose: the package is a beta

    @classmethod
    def load(cls, path: Path) -> "Policy":
        d = json.loads(path.read_text(encoding="utf-8"))
        bad = [r for r in d.get("allow", []) if r not in RISKS]
        if bad:
            raise ValueError(f"Unknown risk(s) in allow: {bad}. Use {list(RISKS)}")
        if not d.get("namespaces"):
            raise ValueError("A policy needs at least one namespace: exposing all 60+ namespaces is not a policy")
        return cls(d["name"], list(d["namespaces"]), d.get("read_only", True), list(d.get("allow", [])),
                   d.get("version", "4.0.0-beta.9"))


def expected_tools(tools: list[Tool], policy: Policy) -> list[Tool]:
    """The tools a --mode all server publishes for this policy (before the three proxied Microsoft Learn tools)."""
    chosen = [t for t in tools if t.namespace in policy.namespaces]
    if policy.read_only:
        chosen = [t for t in chosen if t.read_only]
    return sorted(chosen, key=lambda t: t.name)


def unknown_namespaces(tools: list[Tool], policy: Policy) -> list[str]:
    known = {t.namespace for t in tools}
    return [n for n in policy.namespaces if n not in known]


def findings(tools: list[Tool], policy: Policy) -> list[tuple[str, Tool]]:
    out = []
    for t in expected_tools(tools, policy):
        for risk in RISKS:
            if getattr(t, risk) and risk not in policy.allow:
                out.append((risk, t))
    return out


def start_args(policy: Policy, mode: str = "all") -> list[str]:
    args = ["server", "start", "--mode", mode]
    for ns in policy.namespaces:
        args += ["--namespace", ns]
    if policy.read_only:
        args.append("--read-only")
    return args


def vscode_mcp_json(policy: Policy) -> dict:
    """The .vscode/mcp.json shape Learn shows for a directory install, with our arguments and a pinned version."""
    return {"servers": {policy.name: {"command": "npx", "args": ["-y", f"@azure/mcp@{policy.version}"] + start_args(policy, "namespace")}}}


def namespace_report(tools: list[Tool], policy: Policy) -> list[dict]:
    rows = []
    for ns in policy.namespaces:
        t = [x for x in tools if x.namespace == ns]
        rows.append({"namespace": ns, "tools": len(t), "read_only": sum(x.read_only for x in t),
                     "writes": sum(not x.read_only for x in t), "destructive": sum(x.destructive for x in t),
                     "secret": sum(x.secret for x in t),
                     "exposed": len([x for x in expected_tools(tools, policy) if x.namespace == ns])})
    return rows
