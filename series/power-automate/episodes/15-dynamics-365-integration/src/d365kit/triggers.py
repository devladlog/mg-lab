"""Dataverse trigger and action settings inside a solution flow: what fires the flow, and where it can go wrong.

The trigger settings are the keys the designer stores for 'When a row is added, modified or deleted'
(subscriptionRequest/*). Their exact spelling is *not documented on Learn*: they follow what episode 13 assumed and have
to be confirmed against an exported flow (see README, "What was not verified").
"""
from __future__ import annotations

import re

from flowkit.lint import definition_of, iter_actions

from .odata import Finding, check_filter, evaluate_filter

MESSAGES = {1: "Create", 2: "Delete", 3: "Update", 4: "Create or Update", 5: "Create or Delete",
            6: "Update or Delete", 7: "Create, Update or Delete"}  # numbering: to confirm from an export
SCOPES = {1: "User", 2: "Business Unit", 3: "Parent: Child Business Unit", 4: "Organization"}
# Lookup columns that exist on the Sales tables used in this episode (Learn: lookups can't be in Select columns)
KNOWN_LOOKUPS = {"ownerid", "owninguser", "owningteam", "owningbusinessunit", "customerid", "parentaccountid",
                 "parentcontactid", "regardingobjectid", "createdby", "modifiedby", "transactioncurrencyid",
                 "originatingleadid", "campaignid", "pricelevelid"}
PRIMARY_KEYS = {"opportunityid", "accountid", "contactid", "leadid", "activityid", "quoteid", "salesorderid",
                "incidentid", "invoiceid"}
WRITE_OPS = {"CreateRecord", "UpdateRecord", "UpdateOnlyRecord", "PatchRecord"}


def trigger_settings(flow: dict) -> list[dict]:
    """One dict per Dataverse row trigger: name, table, message, scope, filter, columns."""
    out = []
    for name, trig in definition_of(flow).get("triggers", {}).items():
        p = (trig.get("inputs") or {}).get("parameters") or {}
        if "subscriptionRequest/entityname" not in p or "subscriptionRequest/message" not in p:
            continue
        cols = [c.strip() for c in str(p.get("subscriptionRequest/filteringattributes", "")).split(",") if c.strip()]
        out.append({"name": name, "table": p["subscriptionRequest/entityname"], "message": p["subscriptionRequest/message"],
                    "scope": p.get("subscriptionRequest/scope"), "filter": p.get("subscriptionRequest/filterexpression", ""),
                    "columns": cols})
    return out


def fires(settings: dict, row_after: dict, changed_columns: list[str] | None = None) -> bool:
    """Would this trigger start a run? Learn: 'Select columns' applies to Update only, the flow runs when any of them is
    *included in the update request* (even with an unchanged value), and the filter expression must be true after the save."""
    msg = MESSAGES.get(settings["message"], "")
    if "Update" not in msg:
        raise ValueError("fires() models Update triggers (message 3, 4, 6 or 7)")
    changed = {c.lower() for c in (changed_columns or [])}
    cols = {c.lower() for c in settings["columns"]}
    if cols and not (cols & changed):
        return False
    return evaluate_filter(settings["filter"], row_after) if settings["filter"] else True


def _norm(table: str) -> str:
    """opportunities (entity set) and opportunity (logical name) are the same table."""
    t = table.lower()
    return t[:-3] + "y" if t.endswith("ies") else t.rstrip("s")


def _writes(flow: dict):
    for name, a, *_ in iter_actions(definition_of(flow).get("actions", {})):
        op = (a.get("inputs") or {}).get("host", {}).get("operationId")
        if op in WRITE_OPS:
            p = a["inputs"].get("parameters", {})
            yield name, p.get("entityName"), {k[5:].split("@")[0] for k in p if k.startswith("item/")}


def lint_flow(flow: dict) -> list[Finding]:
    out: list[Finding] = []
    for s in trigger_settings(flow):
        where = f"trigger {s['name']}"
        for f in check_filter(s["filter"]):
            out.append(Finding(f.level, f.code, f"{where}: {f.message}"))
        lookups = [c for c in s["columns"] if c.lower() in KNOWN_LOOKUPS or re.fullmatch(r"_\w+_value", c)]
        if lookups:
            out.append(Finding("error", "D365001", f"{where}: Select columns lists lookup column(s) {lookups}: "
                               "changes to lookups don't trigger the flow (Learn). Use a scalar column"))
        if "Update" in MESSAGES.get(s["message"], "") and not s["columns"]:
            out.append(Finding("warning", "D365002", f"{where}: no Select columns on an update trigger: every update of "
                               "the row can start a run (Learn: use filter columns to prevent unnecessary runs)"))
        keys = [c for c in s["columns"] if c.lower() in PRIMARY_KEYS]
        if keys:
            out.append(Finding("error", "D365003", f"{where}: Select columns lists the primary key {keys}: it is part of "
                               "every update, so every update triggers the flow (Learn)"))
        if s["scope"] not in SCOPES:
            out.append(Finding("warning", "D365004", f"{where}: scope {s['scope']!r} is not one of {sorted(SCOPES)}"))
        # heuristic, not a Learn rule: the flow writes back to the table that triggers it
        if "Update" in MESSAGES.get(s["message"], ""):
            for name, table, cols in _writes(flow):
                if table and _norm(table) == _norm(s["table"]) and (
                        not s["columns"] or {c.lower() for c in cols} & {c.lower() for c in s["columns"]}):
                    out.append(Finding("warning", "D365005", f"{where}: action {name} writes {sorted(cols)} to the table "
                               "that triggers the flow and touches a trigger column: the flow can start itself"))
    for name, a, *_ in iter_actions(definition_of(flow).get("actions", {})):
        for k, v in ((a.get("inputs") or {}).get("parameters") or {}).items():
            if k.endswith("@odata.bind") and not re.match(r"^[a-z][a-z0-9_]*\(.+\)$", str(v)):
                out.append(Finding("error", "D365006", f"action {name}: {k} must look like entitysetname(id), "
                                   f"got {str(v)[:40]!r} (Learn, Add a new row > Set lookup fields)"))
    return out
