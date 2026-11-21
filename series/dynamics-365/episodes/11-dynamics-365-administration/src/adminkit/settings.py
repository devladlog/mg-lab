"""Environment settings that matter to an admin, read from the single row of the organization table.

Columns (Learn, Organization table reference + "Configure auditing"): isauditenabled, auditretentionperiodv2
(days, -1 = forever, valid 1..365000), isuseraccessauditenabled, plugintracelogsetting (0 Off, 1 Exception, 2 All),
sessiontimeoutenabled / sessiontimeoutinmins, inactivitytimeoutenabled / inactivitytimeoutinmins.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .findings import Finding
from .webapi import WebApi

SELECT = ("organizationid,name,isauditenabled,isuseraccessauditenabled,isreadauditenabled,auditretentionperiodv2,"
          "plugintracelogsetting,sessiontimeoutenabled,sessiontimeoutinmins,inactivitytimeoutenabled,"
          "inactivitytimeoutinmins")
TRACE = {0: "Off", 1: "Exception", 2: "All"}
FOREVER = -1
MAX_RETENTION_DAYS = 365000


def fetch(api: WebApi) -> Dict[str, Any]:
    rows = api.get(f"organizations?$select={SELECT}")["value"]
    if len(rows) != 1:  # Learn: the organization table contains a single row
        raise ValueError(f"expected one organization row, got {len(rows)}")
    return rows[0]


def retention_label(days: Any) -> str:
    if days is None:
        return "not set"
    return "forever" if days == FOREVER else f"{days} days"


def describe(org: Dict[str, Any]) -> List[str]:
    yn = lambda v: "on" if v else "off"  # noqa: E731
    trace = TRACE.get(org.get("plugintracelogsetting"), str(org.get("plugintracelogsetting")))
    return [
        f"organization            {org.get('name', '?')}",
        f"auditing                {yn(org.get('isauditenabled'))}",
        f"  user access auditing  {yn(org.get('isuseraccessauditenabled'))}",
        f"  read auditing         {yn(org.get('isreadauditenabled'))}",
        f"  retention             {retention_label(org.get('auditretentionperiodv2'))}",
        f"plug-in trace log       {trace}",
        f"session timeout         {yn(org.get('sessiontimeoutenabled'))}"
        + (f" ({org.get('sessiontimeoutinmins')} min)" if org.get("sessiontimeoutenabled") else ""),
        f"inactivity timeout      {yn(org.get('inactivitytimeoutenabled'))}"
        + (f" ({org.get('inactivitytimeoutinmins')} min)" if org.get("inactivitytimeoutenabled") else ""),
    ]


def check(org: Dict[str, Any], cfg: Dict[str, Any]) -> List[Finding]:
    out: List[Finding] = []
    name = org.get("name", "organization")
    audit = cfg["audit"]
    enabled = bool(org.get("isauditenabled"))
    if audit["require_enabled"] and not enabled:
        out.append(Finding("error", "S001", name, "auditing is off for the environment (Learn: the default is off); "
                           "table and column auditing do nothing until this is on"))
    days = org.get("auditretentionperiodv2")
    if enabled and days is not None and days != FOREVER and days < audit["min_retention_days"]:
        out.append(Finding("warning", "S002", name, f"audit retention is {days} days, team minimum is "
                           f"{audit['min_retention_days']} (Learn: a change only applies to records created afterwards)"))
    if enabled and not org.get("isuseraccessauditenabled"):
        out.append(Finding("info", "S003", name, "user access auditing is off (sign-ins are not logged)"))
    trace = TRACE.get(org.get("plugintracelogsetting"), "?")
    if trace not in cfg["plugin_trace_allowed"]:
        out.append(Finding("warning", "S004", name, f"plug-in trace log is '{trace}'; Learn: trace logging takes up "
                           "storage, turn it on only for troubleshooting and off afterwards"))
    if cfg.get("session_timeout_expected") and not org.get("sessiontimeoutenabled") \
            and not org.get("inactivitytimeoutenabled"):
        out.append(Finding("info", "S005", name, "no session or inactivity timeout is configured"))
    return out


def validate_retention(days: int) -> int:
    if days != FOREVER and not (1 <= days <= MAX_RETENTION_DAYS):
        raise ValueError(f"retention must be -1 (forever) or 1..{MAX_RETENTION_DAYS} days, got {days}")
    return days


def audit_body(days: int) -> Dict[str, Any]:
    return {"isauditenabled": True, "auditretentionperiodv2": validate_retention(days)}


def enable_audit(api: WebApi, days: int, *, apply: bool, out=print) -> Dict[str, Any]:
    """Turn environment auditing on and set the retention. Dry run unless apply; reads back after applying.

    Needs System Administrator or System Customizer (Learn). Only the environment-level switch is set here: tables
    and columns still need 'Audit changes to its data' / 'Enable auditing' (Learn, Manage Dataverse auditing).
    """
    body = audit_body(days)
    org = fetch(api)
    out(f"before: auditing {'on' if org.get('isauditenabled') else 'off'}, "
        f"retention {retention_label(org.get('auditretentionperiodv2'))}")
    if not apply:
        out(f"dry run: would set auditing on, retention {retention_label(days)} (add --apply)")
        return org
    api.update(f"organizations({org['organizationid']})", body)
    after = fetch(api)
    out(f"after:  auditing {'on' if after.get('isauditenabled') else 'off'}, "
        f"retention {retention_label(after.get('auditretentionperiodv2'))}")
    if after.get("isauditenabled") != body["isauditenabled"] or after.get("auditretentionperiodv2") != days:
        raise ValueError("read-back does not match what was sent")
    return after
