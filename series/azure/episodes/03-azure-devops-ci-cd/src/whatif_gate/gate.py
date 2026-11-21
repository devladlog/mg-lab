"""
What-if gate: read the JSON of `az deployment group what-if --no-pretty-print` and decide whether the
deployment may continue.

Rules (all from a small JSON policy file, see pipelines/gate-policy.json):
  * change types in `block_change_types` (Delete) always stop the run
  * a change that touches a protected property (by resource type + property path prefix) stops the run,
    unless the run was queued with "accept protected changes" ticked (a runtime parameter in the pipeline)
  * change types in `warn_change_types` (Unsupported) and unevaluated expressions are reported as warnings
  * property paths in `ignore_paths` are treated as known noise and never count as protected changes

The output is a Markdown summary (uploaded to the run with ##vso[task.uploadsummary]) and an exit code:
0 = go, 1 = blocked, 2 = the what-if output itself is unusable.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

CHANGE_TYPES = ["Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "NoEffect", "Unsupported"]


class WhatIfFormatError(ValueError):
    """The input isn't a what-if result we can trust."""


@dataclass(frozen=True)
class Protected:
    resource_type: str          # e.g. Microsoft.Storage/storageAccounts (case-insensitive, globs allowed)
    paths: tuple[str, ...]      # property path prefixes, e.g. properties.publicNetworkAccess
    change_types: tuple[str, ...] = ("Modify", "Delete")


@dataclass(frozen=True)
class Policy:
    block_change_types: tuple[str, ...] = ("Delete",)
    warn_change_types: tuple[str, ...] = ("Unsupported",)
    protected: tuple[Protected, ...] = ()
    ignore_paths: tuple[str, ...] = ()

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Policy":
        unknown = set(data) - {"block_change_types", "warn_change_types", "protected", "ignore_paths", "$comment"}
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        protected = tuple(
            Protected(p["resource_type"], tuple(p["paths"]), tuple(p.get("change_types", ("Modify", "Delete"))))
            for p in data.get("protected", [])
        )
        for p in protected:
            bad = set(p.change_types) - set(CHANGE_TYPES)
            if bad:
                raise ValueError(f"unknown change types in policy: {sorted(bad)}")
        return Policy(
            block_change_types=tuple(data.get("block_change_types", ("Delete",))),
            warn_change_types=tuple(data.get("warn_change_types", ("Unsupported",))),
            protected=protected,
            ignore_paths=tuple(data.get("ignore_paths", ())),
        )


@dataclass
class Finding:
    level: str                  # "block" | "warn"
    resource: str               # short name: type/name
    message: str


@dataclass
class GateResult:
    counts: dict[str, int]
    resources: list[tuple[str, str]]            # (change type, short resource name)
    findings: list[Finding] = field(default_factory=list)
    accepted: list[Finding] = field(default_factory=list)   # protected changes let through on purpose

    @property
    def blocked(self) -> bool:
        return any(f.level == "block" for f in self.findings)


def load_changes(doc: Any) -> list[dict[str, Any]]:
    """Accept both shapes: the Azure CLI output ({"changes": [...]}) and the REST body ({"properties": {...}})."""
    if not isinstance(doc, dict):
        raise WhatIfFormatError("what-if output must be a JSON object")
    if doc.get("error"):
        err = doc["error"]
        raise WhatIfFormatError(f"what-if failed: {err.get('code', '?')}: {err.get('message', '')}".strip())
    status = doc.get("status")
    if status and status != "Succeeded":
        raise WhatIfFormatError(f"what-if status is {status!r}, not 'Succeeded'")
    changes = doc.get("changes")
    if changes is None and isinstance(doc.get("properties"), dict):
        changes = doc["properties"].get("changes")
    if not isinstance(changes, list):
        raise WhatIfFormatError("no 'changes' list in the what-if output")
    for c in changes:
        if not isinstance(c, dict) or c.get("changeType") not in CHANGE_TYPES or not c.get("resourceId"):
            raise WhatIfFormatError(f"malformed change entry: {json.dumps(c)[:200]}")
    return changes


def resource_type(resource_id: str) -> str:
    """'/subscriptions/../providers/Microsoft.Web/sites/app-1/config/web' -> 'Microsoft.Web/sites/config'."""
    parts = resource_id.strip("/").split("/")
    try:
        i = len(parts) - 1 - parts[::-1].index("providers")
    except ValueError:
        return "Microsoft.Resources/resourceGroups" if "resourceGroups" in parts else "unknown"
    namespace, rest = parts[i + 1], parts[i + 2:]
    return "/".join([namespace, *rest[0::2]])


def short_name(resource_id: str) -> str:
    parts = resource_id.strip("/").split("/")
    return f"{resource_type(resource_id)}/{parts[-1]}"


def flatten(delta: Iterable[dict[str, Any]], prefix: str = "") -> Iterable[tuple[str, str, Any, Any]]:
    """Yield (full path, propertyChangeType, before, after) for every leaf change, walking Array children."""
    for d in delta or []:
        path = d.get("path", "")
        full = f"{prefix}.{path}" if prefix and path else (path or prefix)
        children = d.get("children")
        if children:
            yield from flatten(children, full)
        else:
            yield full, d.get("propertyChangeType", "Modify"), d.get("before"), d.get("after")


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")


def _unevaluated(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("[") and value.endswith("]") and "(" in value


def evaluate(doc: Any, policy: Policy, accept_protected: bool = False) -> GateResult:
    changes = load_changes(doc)
    counts = {t: 0 for t in CHANGE_TYPES}
    resources: list[tuple[str, str]] = []
    result = GateResult(counts=counts, resources=resources)

    for c in changes:
        ctype, rid = c["changeType"], c["resourceId"]
        rtype, name = resource_type(rid), short_name(rid)
        counts[ctype] += 1
        if ctype not in ("NoChange", "Ignore"):
            resources.append((ctype, name))

        if ctype in policy.block_change_types:
            result.findings.append(Finding("block", name, f"{ctype} is never done by this pipeline"))
            continue
        if ctype in policy.warn_change_types:
            reason = c.get("unsupportedReason") or "what-if can't predict this resource"
            result.findings.append(Finding("warn", name, f"{ctype}: {reason}"))

        leaves = [leaf for leaf in flatten(c.get("delta", []))
                  if not any(_matches(leaf[0], ip) for ip in policy.ignore_paths)]
        for path, _, before, after in leaves:
            if _unevaluated(after):
                result.findings.append(Finding("warn", name, f"{path} is an unevaluated expression {after}"))

        for rule in policy.protected:
            if not fnmatch.fnmatch(rtype.lower(), rule.resource_type.lower()) or ctype not in rule.change_types:
                continue
            if ctype == "Delete":
                hits = ["(resource)"]
            else:
                hits = sorted({p for p, *_ in leaves if any(_matches(p, rp) for rp in rule.paths)})
            for path in hits:
                before, after = next(((b, a) for p, _, b, a in leaves if p == path), (None, None))
                msg = f"protected change {path}: {json.dumps(before)} -> {json.dumps(after)}"
                finding = Finding("block", name, msg)
                (result.accepted if accept_protected else result.findings).append(finding)
    return result


def to_markdown(result: GateResult, title: str) -> str:
    verdict = "BLOCKED" if result.blocked else "GO"
    lines = [f"## {title}: {verdict}", "", "| Change type | Count |", "|---|---:|"]
    lines += [f"| {t} | {n} |" for t, n in result.counts.items() if n]
    if result.resources:
        lines += ["", "| Change | Resource |", "|---|---|"]
        lines += [f"| {t} | `{n}` |" for t, n in sorted(result.resources)]
    if result.findings:
        lines += ["", "### Findings", ""]
        lines += [f"- **{f.level}** `{f.resource}`: {f.message}" for f in result.findings]
    if result.accepted:
        lines += ["", "### Protected changes accepted for this run", ""]
        lines += [f"- `{f.resource}`: {f.message}" for f in result.accepted]
    return "\n".join(lines) + "\n"


def logging_commands(result: GateResult) -> list[str]:
    """Azure Pipelines logging commands (one line each, ';' and newlines escaped as Learn documents)."""
    def esc(s: str) -> str:
        return s.replace("%", "%AZP25").replace(";", "%3B").replace("\r", "%0D").replace("\n", "%0A").replace("]", "%5D")
    out = []
    for f in result.findings:
        level = "error" if f.level == "block" else "warning"
        out.append(f"##vso[task.logissue type={level}]{esc(f.resource + ': ' + f.message)}")
    for f in result.accepted:
        out.append(f"##vso[task.logissue type=warning]{esc('accepted ' + f.resource + ': ' + f.message)}")
    return out
