"""Which connectors a flow uses, and whether the policies that apply would suspend it.

Rules (Learn, "Implement a data policy strategy" and "Combined effect of multiple data policies"):
 * a connector that any applicable policy marks Blocked can't be used at all;
 * otherwise every connector in the flow must be in the same group, in every applicable policy
   (with several policies the groups multiply: 2^n combinations, only identical combinations mix).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from flowkit.lint import definition_of, iter_actions

from .connectors import HTTP, display, norm_id
from .model import BLOCKED, Policy


@dataclass
class Usage:
    connectors: set[str] = field(default_factory=set)
    not_evaluated: list[str] = field(default_factory=list)   # things a policy governs but we can't resolve


@dataclass
class Violation:
    kind: str       # "blocked" | "mixed"
    message: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


def connectors_of(flow: dict) -> Usage:
    """Connector ids used by triggers and actions (not the ones only declared in connectionReferences)."""
    d = definition_of(flow)
    refs = (flow.get("properties") or {}).get("connectionReferences") or {}
    use = Usage()

    def one(name: str, node: dict, is_trigger: bool):
        t = node.get("type")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if t in ("OpenApiConnection", "OpenApiConnectionWebhook", "OpenApiConnectionNotification",
                 "ApiConnection", "ApiConnectionWebhook"):
            cname = (inputs.get("host") or {}).get("connectionName")
            api = ((refs.get(cname) or {}).get("api") or {}).get("name") if cname else None
            if cname or api:
                use.connectors.add(norm_id(api or cname))
        elif t == "Http":
            use.connectors.add(HTTP)
        elif t == "HttpWebhook":
            use.not_evaluated.append(f"{name}: HTTP Webhook (connector id not on Learn)")
        elif t == "Request" and node.get("kind") == "Http":
            use.not_evaluated.append(f"{name}: When an HTTP request is received (connector id not on Learn)")
        elif t == "Workflow":
            use.not_evaluated.append(f"{name}: child flow (Learn: a violation anywhere in the flow tree suspends the parent; "
                                     f"run dlpkit on the child flow too)")

    for tname, trig in (d.get("triggers") or {}).items():
        one(tname, trig, True)
    for name, action, *_ in iter_actions(d.get("actions") or {}):
        one(name, action, False)
    return use


def evaluate(connectors: set[str], policies: list[Policy], environment: str | None = None,
             what_if: dict[str, str] | None = None) -> list[Violation]:
    """`what_if` maps connector id -> group, applied on top of every policy (to try a change before making it)."""
    pols = sorted((p for p in policies if p.applies_to(environment)), key=lambda p: p.display_name)
    names: dict[str, str] = {}
    for p in pols:
        names.update(p.names)

    def grp(p: Policy, c: str) -> str:
        return (what_if or {}).get(c) or p.group(c)

    out: list[Violation] = []
    live: list[str] = []
    for c in sorted(connectors):
        blockers = [p.display_name for p in pols if grp(p, c) == BLOCKED]
        if blockers:
            out.append(Violation("blocked", f"{display(c, names)} is blocked by {', '.join(repr(b) for b in blockers)}"))
        else:
            live.append(c)
    sig = {c: tuple(grp(p, c) for p in pols) for c in live}
    if len(set(sig.values())) > 1:
        by_sig: dict[tuple, list[str]] = {}
        for c, s in sig.items():
            by_sig.setdefault(s, []).append(display(c, names))
        parts = []
        for s, members in by_sig.items():
            label = s[0] if len(s) == 1 else "; ".join(f"{pol.display_name}: {g}" for pol, g in zip(pols, s))
            parts.append(f"{', '.join(sorted(members))} ({label})")
        out.append(Violation("mixed", "connectors from different groups can't be used together: " + " | ".join(sorted(parts))))
    return out


def consolidated_groups(connectors: list[str], policies: list[Policy], environment: str | None = None) -> list[list[str]]:
    """The groups that several policies leave you with (Learn's three-policy example gives eight possible groups)."""
    pols = sorted((p for p in policies if p.applies_to(environment)), key=lambda p: p.display_name)
    buckets: dict[tuple, list[str]] = {}
    for c in connectors:
        buckets.setdefault(tuple(p.group(c) for p in pols), []).append(c)
    return [sorted(v) for _, v in sorted(buckets.items())]
