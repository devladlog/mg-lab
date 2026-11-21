"""Check the Web API `fields` of each enabled table against the real columns of the Dataverse table.

A misspelt column in `Webapi/<table>/fields` is a portal-side failure you only meet in the browser. The table's
column list comes from the Dataverse metadata (EntityDefinitions ... /Attributes), which is the same environment the
site is connected to. Lookup columns are listed by their logical name there (the Web API response then names them
`_<name>_value`, which Learn documents).
"""
from __future__ import annotations

from typing import Dict, List, Set

from .lint import Finding
from .siteconfig import Site
from .webapi import DataverseError, WebApi


def table_columns(api: WebApi, table: str) -> Set[str]:
    data = api.get(f"EntityDefinitions(LogicalName='{table}')/Attributes?$select=LogicalName")
    return {a["LogicalName"] for a in data.get("value", [])}


def check(api: WebApi, site: Site) -> List[Finding]:
    out: List[Finding] = []
    for table, ts in sorted(site.settings.items()):
        if not ts.is_enabled or not ts.field_list or "*" in ts.field_list:
            continue
        try:
            cols = table_columns(api, table)
        except DataverseError as e:
            out.append(Finding("error", "F002", f"Webapi/{table}", f"cannot read the table metadata: {e}"))
            continue
        missing = [f for f in ts.field_list if f not in cols]
        if missing:
            out.append(Finding("error", "F001", f"Webapi/{table}", f"not a column of '{table}': {', '.join(missing)}"))
    return out
