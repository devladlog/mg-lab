"""A data policy, as far as flows are concerned: which group each connector is in, and where it applies."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .connectors import UNBLOCKABLE, norm_id

# The PowerShell cmdlets name the groups General (Non-business), Confidential (Business) and Blocked
# (Learn: Add-ConnectorsToPolicy, -Classification).
GROUP = {"confidential": "Business", "general": "Non-business", "blocked": "Blocked",
         "business": "Business", "non-business": "Non-business", "nonbusiness": "Non-business"}
BUSINESS, NONBUSINESS, BLOCKED = "Business", "Non-business", "Blocked"


class PolicyError(Exception):
    pass


def group_of(label: str) -> str:
    try:
        return GROUP[str(label).strip().lower()]
    except KeyError:
        raise PolicyError(f"unknown classification {label!r} (use General, Confidential or Blocked)") from None


@dataclass
class Policy:
    display_name: str
    default: str = NONBUSINESS
    groups: dict[str, str] = field(default_factory=dict)   # connector id -> group (explicit entries only)
    names: dict[str, str] = field(default_factory=dict)    # connector id -> display name, when the file has it
    scope_mode: str = "all"                                # all | only | except
    environments: tuple[str, ...] = ()
    policy_id: str = ""

    def applies_to(self, environment: str | None) -> bool:
        if self.scope_mode == "all" or environment is None:
            return True
        listed = environment.lower() in {e.lower() for e in self.environments}
        return listed if self.scope_mode == "only" else not listed

    def group(self, cid: str) -> str:
        """Effective group. A connector that isn't in any list is in the default group; Learn: a connector that
        can't be blocked lands in Non-business when the default group is Blocked."""
        cid = norm_id(cid)
        g = self.groups.get(cid, self.default)
        if g == BLOCKED and cid in UNBLOCKABLE and cid not in self.groups:
            return NONBUSINESS
        return g


def policy_from_dict(d: dict) -> Policy:
    """Accepts the shape Get-DlpPolicy returns (name, displayName, defaultConnectorsClassification,
    connectorGroups[].classification / connectors[].id) plus an optional `scope` we add:
    {"mode": "all|only|except", "environments": [...]}."""
    if "displayName" not in d:
        raise PolicyError("policy has no displayName")
    p = Policy(display_name=d["displayName"], policy_id=str(d.get("name", "")))
    p.default = group_of(d.get("defaultConnectorsClassification", "General"))
    for grp in d.get("connectorGroups") or []:
        g = group_of(grp["classification"])
        for c in grp.get("connectors") or []:
            cid = norm_id(c["id"])
            if cid in p.groups and p.groups[cid] != g:
                raise PolicyError(f"{p.display_name}: connector {cid} is in two groups")
            p.groups[cid] = g
            if c.get("name"):
                p.names[cid] = c["name"]
    scope = d.get("scope") or {}
    p.scope_mode = scope.get("mode", "all")
    if p.scope_mode not in ("all", "only", "except"):
        raise PolicyError(f"{p.display_name}: scope.mode must be all, only or except")
    p.environments = tuple(scope.get("environments") or ())
    return p


def load_policies(*paths: str | Path) -> list[Policy]:
    out: list[Policy] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        items = data.get("value", [data]) if isinstance(data, dict) else data   # Get-DlpPolicy output is {value: [...]}
        out += [policy_from_dict(i) for i in items]
    return out


def validate(p: Policy) -> list[str]:
    """Problems the admin center would also refuse (Learn: an unblockable connector in the Blocked group stops you from saving)."""
    problems = []
    for cid, g in p.groups.items():
        if g == BLOCKED and cid in UNBLOCKABLE:
            problems.append(f"{p.display_name}: {p.names.get(cid, cid)} can't be blocked; put it in Business or Non-business")
    return problems
