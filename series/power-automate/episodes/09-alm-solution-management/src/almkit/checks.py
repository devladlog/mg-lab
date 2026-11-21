"""Rules a solution must pass before it leaves DEV. Each one comes from Microsoft Learn or from a failure we hit
(the README says which). Nothing here needs a tenant."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import settings as st
from .model import ROOT_ENV_VAR, ROOT_FLOW, Solution, SolutionError, parse_version


@dataclass
class Finding:
    level: str  # error | warning
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.where}: {self.message}"


ZERO_GUID = re.compile(r"^0{8}-0{4}-0{4}-0{4}-[0-9]+$|^0{8}-0{4}-0{4}-0{4}-0{12}$")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SHAREPOINT_URL = re.compile(r"https?://[A-Za-z0-9.-]+\.sharepoint\.com[^\s'\"]*", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _actions(actions: dict):
    for name, a in (actions or {}).items():
        yield name, a
        for key in ("actions",):
            yield from _actions(a.get(key, {}))
        yield from _actions(a.get("else", {}).get("actions", {}))
        for case in a.get("cases", {}).values():
            yield from _actions(case.get("actions", {}))
        yield from _actions(a.get("default", {}).get("actions", {}))


def check_solution(sol: Solution) -> list[Finding]:
    out: list[Finding] = []
    err = lambda code, where, msg: out.append(Finding("error", code, where, msg))
    warn = lambda code, where, msg: out.append(Finding("warning", code, where, msg))

    # A01 version
    try:
        parse_version(sol.version_text)
    except SolutionError as e:
        err("A01", "Solution.xml", str(e))

    # A02 package type: only a folder unpacked as Both can be packed as Managed
    if sol.managed != "2":
        err("A02", "Solution.xml",
            f"<Managed>{sol.managed}</Managed>: `pac solution pack --packagetype Managed` fails on this folder "
            "('Solution package type did not match requested type'). Export the solution twice (unmanaged and "
            "managed) and unpack with --packagetype Both.")

    # A03 prefix
    if not sol.prefix:
        err("A03", "Solution.xml", "the publisher has no customization prefix")
    for name in list(sol.env_vars) + list(sol.conn_refs):
        if sol.prefix and not name.startswith(sol.prefix + "_"):
            err("A03", name, f"doesn't start with the publisher prefix '{sol.prefix}_' (another publisher's component?)")

    # A04 root components and files agree
    if set(sol.flows) != sol.root_flows:
        err("A04", "Solution.xml", f"flows in Workflows/ {sorted(sol.flows)} != root components of type {ROOT_FLOW} "
                                   f"{sorted(sol.root_flows)}")
    if set(sol.env_vars) != sol.root_env_vars:
        err("A04", "Solution.xml", f"environment variables on disk {sorted(sol.env_vars)} != root components of type "
                                   f"{ROOT_ENV_VAR} {sorted(sol.root_env_vars)}")

    used_env: set[str] = set()
    used_refs: set[str] = set()
    for flow in sol.flows.values():
        where = flow.file.name
        props = flow.body["properties"]
        definition = props["definition"]

        # A05 connection references only
        for key, ref in flow.connection_references.items():
            logical = (ref.get("connection") or {}).get("connectionReferenceLogicalName")
            if not logical:
                err("A05", f"{where} connectionReferences.{key}",
                    "binds a connection directly instead of a connection reference "
                    "(solution flows bind to connection references, so each environment can supply its own connection)")
                continue
            used_refs.add(logical)
            if logical not in sol.conn_refs:
                err("A05", f"{where} connectionReferences.{key}",
                    f"connection reference '{logical}' isn't in Customizations.xml")
            elif not sol.conn_refs[logical].endswith("/" + key):
                err("A05", f"{where} connectionReferences.{key}",
                    f"connector of '{logical}' is {sol.conn_refs[logical]}, the flow uses {key}")
        for name, a in _actions(definition.get("actions", {})):
            host = (a.get("inputs") or {}).get("host") if isinstance(a.get("inputs"), dict) else None
            if host and host.get("connectionName") not in flow.connection_references:
                err("A05", f"{where} {name}", f"connectionName {host.get('connectionName')!r} has no entry in connectionReferences")

        # A06 nothing typed into actions that differs per environment
        for part in ("triggers", "actions"):
            for text in _strings(definition.get(part, {})):
                if text.startswith("@parameters("):
                    continue
                for pat, what in ((SHAREPOINT_URL, "a SharePoint URL"), (EMAIL, "an email address"), (GUID, "a GUID")):
                    for m in pat.finditer(text):
                        if what == "a GUID" and ZERO_GUID.match(m.group(0)):
                            continue
                        err("A06", where, f"{what} typed into the flow ({m.group(0)!r}): put it in an environment variable")

        # A07 parameters agree with the definitions
        for pname, p in definition.get("parameters", {}).items():
            schema = (p.get("metadata") or {}).get("schemaName")
            if not schema:
                continue
            used_env.add(schema)
            if schema not in sol.env_vars:
                err("A07", where, f"parameter '{pname}' uses {schema}, which isn't defined in the solution")
            elif p.get("defaultValue") != sol.env_vars[schema].default:
                err("A07", where, f"{schema}: flow default {p.get('defaultValue')!r} != definition default "
                                  f"{sol.env_vars[schema].default!r}")
        # every @parameters('...') in an expression must be declared
        declared = set(definition.get("parameters", {}))
        for text in _strings({k: definition.get(k) for k in ("triggers", "actions")}):
            for ref in re.findall(r"parameters\('([^']+)'\)", text):
                if ref not in declared:
                    err("A07", where, f"expression uses parameters('{ref}'), which the flow doesn't declare")

    for schema, ev in sol.env_vars.items():
        # A08 current values must not ship (Learn: "Should I include the value in my solution? No.")
        if ev.extra_files:
            err("A08", schema, f"ships a value ({', '.join(ev.extra_files)}): remove the current value before export, "
                               "so each environment supplies its own")
        if schema not in used_env:
            warn("A09", schema, "no flow uses this environment variable")
    for logical in sol.conn_refs:
        if logical not in used_refs:
            warn("A09", logical, "no flow uses this connection reference")
    return out


def check_settings(sol: Solution, data: dict, name: str, rendered: bool = True) -> list[Finding]:
    """`rendered=False` accepts ${TOKENS} (a committed template); True is what the import will really read."""
    out: list[Finding] = []
    err = lambda code, msg: out.append(Finding("error", code, name, msg))
    warn = lambda code, msg: out.append(Finding("warning", code, name, msg))
    if set(data) - {"EnvironmentVariables", "ConnectionReferences"}:
        warn("S01", f"unexpected keys {sorted(set(data) - {'EnvironmentVariables', 'ConnectionReferences'})}")
    envs = {e.get("SchemaName"): e for e in data.get("EnvironmentVariables", [])}
    refs = {c.get("LogicalName"): c for c in data.get("ConnectionReferences", [])}

    for schema in sol.env_vars:
        if schema not in envs:
            err("S02", f"{schema} has no entry: the import would use the default value "
                       f"({sol.env_vars[schema].default!r}) or ask for one")
    for schema in envs:
        if schema not in sol.env_vars:
            err("S02", f"{schema} isn't an environment variable of {sol.unique_name} {sol.version_text}")
    for schema, e in envs.items():
        v = e.get("Value")
        if v is None or v == "":
            if schema in sol.env_vars:
                warn("S03", f"{schema} has an empty Value (Learn: values shown as \"\" are missing)")
        elif not rendered and st.tokens_in(str(v)):
            pass
        elif st.tokens_in(str(v)):
            err("S03", f"{schema} still has an unresolved token {st.tokens_in(str(v))}")

    for logical, cid in sol.conn_refs.items():
        if logical not in refs:
            err("S04", f"{logical} has no entry: the flows that use it can't be turned on without a connection")
    for logical, c in refs.items():
        if logical not in sol.conn_refs:
            err("S04", f"{logical} isn't a connection reference of {sol.unique_name} {sol.version_text}")
            continue
        if c.get("ConnectorId") != sol.conn_refs[logical]:
            err("S05", f"{logical}: ConnectorId {c.get('ConnectorId')!r} != {sol.conn_refs[logical]!r}")
        cid = c.get("ConnectionId") or ""
        if not cid:
            err("S06", f"{logical}: ConnectionId is empty")
        elif st.tokens_in(cid):
            if rendered:
                err("S06", f"{logical}: ConnectionId still has an unresolved token {st.tokens_in(cid)}")
        elif not st.CONNECTION_ID.match(cid):
            err("S06", f"{logical}: ConnectionId {cid!r} doesn't look like a connection ID (32 hex digits, "
                       "copied from the connection's URL in the target environment)")
    return out


def check_version_bump(old: Solution, new: Solution) -> list[Finding]:
    if new.unique_name != old.unique_name:
        return [Finding("error", "V01", new.unique_name, f"unique name changed from {old.unique_name}: that is a different solution")]
    if new.version <= old.version:
        return [Finding("error", "V02", "Solution.xml",
                        f"version {new.version_text} is not higher than {old.version_text}: the import of an update "
                        "needs a higher major, minor, build or revision number (Learn)")]
    return []


def settings_file(path) -> dict:
    return json.loads(open(path, encoding="utf-8-sig").read())
