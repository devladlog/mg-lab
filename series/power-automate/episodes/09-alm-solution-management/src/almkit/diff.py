"""What changes between two releases, and whether Update is enough or the target needs Upgrade."""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Solution


@dataclass
class Plan:
    old: str
    new: str
    flows_added: list[str] = field(default_factory=list)
    flows_removed: list[str] = field(default_factory=list)
    flows_changed: list[str] = field(default_factory=list)
    env_added: list[str] = field(default_factory=list)
    env_removed: list[str] = field(default_factory=list)
    env_default_changed: list[str] = field(default_factory=list)
    refs_added: list[str] = field(default_factory=list)
    refs_removed: list[str] = field(default_factory=list)

    @property
    def needs_upgrade(self) -> bool:
        """Learn: an update can't delete components; only an upgrade removes what the new version no longer has."""
        return bool(self.flows_removed or self.env_removed or self.refs_removed)

    @property
    def needs_new_settings(self) -> bool:
        return bool(self.env_added or self.refs_added)

    def lines(self) -> list[str]:
        out = [f"{self.old} -> {self.new}"]
        for label, items in (("flow added", self.flows_added), ("flow removed", self.flows_removed),
                             ("flow changed", self.flows_changed), ("environment variable added", self.env_added),
                             ("environment variable removed", self.env_removed),
                             ("environment variable default changed", self.env_default_changed),
                             ("connection reference added", self.refs_added),
                             ("connection reference removed", self.refs_removed)):
            out += [f"  {label}: {i}" for i in items]
        out.append("  import mode: " + ("UPGRADE (components were removed; an update would leave them in the target)"
                                        if self.needs_upgrade else "update or upgrade (nothing was removed)"))
        if self.needs_new_settings:
            out.append("  settings files need new entries: " + ", ".join(self.env_added + self.refs_added))
        return out


def plan(old: Solution, new: Solution) -> Plan:
    p = Plan(f"{old.unique_name} {old.version_text}", f"{new.unique_name} {new.version_text}")
    names = lambda s: {fid: f.name for fid, f in s.flows.items()}
    on, nn = names(old), names(new)
    p.flows_added = sorted(nn[i] for i in nn.keys() - on.keys())
    p.flows_removed = sorted(on[i] for i in on.keys() - nn.keys())
    p.flows_changed = sorted(nn[i] for i in nn.keys() & on.keys() if old.flows[i].digest != new.flows[i].digest)
    p.env_added = sorted(new.env_vars.keys() - old.env_vars.keys())
    p.env_removed = sorted(old.env_vars.keys() - new.env_vars.keys())
    p.env_default_changed = sorted(s for s in new.env_vars.keys() & old.env_vars.keys()
                                   if new.env_vars[s].default != old.env_vars[s].default)
    p.refs_added = sorted(new.conn_refs.keys() - old.conn_refs.keys())
    p.refs_removed = sorted(old.conn_refs.keys() - new.conn_refs.keys())
    return p
