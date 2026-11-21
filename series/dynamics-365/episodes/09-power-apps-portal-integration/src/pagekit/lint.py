"""Rules for a Power Pages site's Web API configuration. Each rule cites what Learn says (see README)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .siteconfig import Site

# Learn, Portals Web API overview: "You can't use Portal Web API for the following configuration tables"
UNSUPPORTED = frozenset("""adx_contentaccesslevel adx_contentsnippet adx_entityform adx_entityformmetadata adx_entitylist
adx_entitypermission adx_entitypermission_webrole adx_externalidentity adx_pagealert adx_pagenotification adx_pagetag
adx_pagetag_webpage adx_pagetemplate adx_portallanguage adx_publishingstate adx_publishingstatetransitionrule
adx_publishingstatetransitionrule_webrole adx_redirect adx_setting adx_shortcut adx_sitemarker adx_sitesetting
adx_urlhistory adx_webfile adx_webfilelog adx_webform adx_webformmetadata adx_webformsession adx_webformstep adx_weblink
adx_weblinkset adx_webnotificationentity adx_webnotificationurl adx_webpage adx_webpage_tag
adx_webpageaccesscontrolrule adx_webpageaccesscontrolrule_webrole adx_webpagehistory adx_webpagelog
adx_webrole_systemuser adx_website adx_website_list adx_website_sponsor adx_websiteaccess adx_websiteaccess_webrole
adx_websitebinding adx_websitelanguage adx_webtemplate""".split())

# the usual mistake: the EntitySetName in a site setting, which wants the logical name
SET_TO_LOGICAL = {"accounts": "account", "contacts": "contact", "incidents": "incident",
                  "opportunities": "opportunity", "leads": "lead", "annotations": "annotation"}


@dataclass
class Finding:
    level: str
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():<7} {self.code}  {self.where}: {self.message}"


def lint(site: Site, expected: Optional[Dict[str, List[str]]] = None) -> List[Finding]:
    out: List[Finding] = []
    for table, ts in sorted(site.settings.items()):
        w = f"Webapi/{table}"
        if table in SET_TO_LOGICAL:
            out.append(Finding("warning", "P008", w, f"'{table}' looks like an EntitySetName; site settings use the "
                                                    f"table logical name ('{SET_TO_LOGICAL[table]}')"))
        if ts.enabled is not None and ts.enabled.strip().lower() not in ("true", "false"):
            out.append(Finding("error", "P009", w, f"enabled is '{ts.enabled}', valid values are True and False"))
        if not ts.is_enabled:
            if ts.fields or ts.view_columns:
                out.append(Finding("warning", "P007", w, "columns configured but the Web API is not enabled for this table"))
            continue
        if table in UNSUPPORTED:
            out.append(Finding("error", "P003", w, "configuration table: the portals Web API does not support it"))
        if "*" in ts.field_list:
            out.append(Finding("error", "P002", w, "fields contains '*': Learn says the wildcard is deprecated and "
                                                   "requests fail until explicit column names are configured"))
        elif not ts.field_list and not ts.view_columns:
            out.append(Finding("error", "P001", w, "enabled without 'fields' (or UseFieldsFromView): Learn says the "
                                                   "fields setting is required"))
        if ts.view_columns:
            out.append(Finding("info", "P010", w, "UseFieldsFromView needs the public system view 'Power Pages Web API "
                                                  "Columns' and site version 9.8.8.x or later; view changes can take up to 5 minutes"))
        perms = [p for p in site.permissions if p.table == table]
        if not perms:
            out.append(Finding("error", "P004", w, "enabled but no table permission for this table: the Web API follows "
                                                   "table permissions, so every call is denied"))
        for p in perms:
            roles = [site.roles.get(r) for r in p.role_ids]
            anon = any(r and r.anonymous for r in roles)
            writes = sorted(p.privileges & {"create", "write", "delete", "append", "appendto"})
            if p.scope == "global" and anon and writes:
                out.append(Finding("error", "P005", p.name, f"Global scope for the Anonymous Users role with "
                                                             f"{'/'.join(writes)} on a Web API table: public write access"))
            elif p.scope == "global":
                who = "Anonymous Users" if anon else "its roles"
                out.append(Finding("warning", "P006", p.name, f"Global scope on a Web API table gives {who} every row; "
                                                              "prefer Contact, Account, Self or Parent scope"))
    if expected is not None:
        for table, cols in sorted(expected.items()):
            ts = site.settings.get(table)
            if ts is None or not ts.is_enabled:
                out.append(Finding("error", "P012", f"Webapi/{table}", "expected to be enabled but is not"))
            elif sorted(ts.field_list) != sorted(cols) and not ts.view_columns:
                extra, missing = sorted(set(ts.field_list) - set(cols)), sorted(set(cols) - set(ts.field_list))
                out.append(Finding("error", "P012", f"Webapi/{table}", "columns differ from portal.json"
                                   + (f"; extra: {', '.join(extra)}" if extra else "")
                                   + (f"; missing: {', '.join(missing)}" if missing else "")))
        for table, ts in sorted(site.settings.items()):
            if ts.is_enabled and table not in expected:
                out.append(Finding("warning", "P013", f"Webapi/{table}", "enabled but not in portal.json: expose only "
                                                                          "the tables the pages need"))
    return out


def summary(findings: Iterable[Finding]) -> str:
    f = list(findings)
    return (f"{sum(x.level == 'error' for x in f)} error(s), {sum(x.level == 'warning' for x in f)} warning(s), "
            f"{sum(x.level == 'info' for x in f)} note(s)")
