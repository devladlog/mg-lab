"""Read $metadata: is Customer Service in this environment, how is CloseIncident defined, which KPI lookups does the case have?"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict

from .webapi import WebApi

EDM = "{http://docs.oasis-open.org/odata/ns/edm}"
TABLES = ("incident", "incidentresolution", "sla", "slakpiinstance", "entitlement", "queue", "queueitem")


def parse(xml: str) -> Dict[str, object]:
    root = ET.fromstring(xml)
    entities, kpi_lookups, close = {}, [], None
    for el in root.iter():
        if el.tag == EDM + "EntityType":
            entities[el.get("Name")] = el
        elif el.tag == EDM + "Action" and el.get("Name") == "CloseIncident":
            params = [(p.get("Name"), p.get("Type")) for p in el.findall(EDM + "Parameter")]
            bound = el.get("IsBound") == "true"
            close = {"bound": bound, "params": params[1:] if bound else params}
    inc = entities.get("incident")
    if inc is not None:
        kpi_lookups = sorted(n.get("Name") for n in inc.findall(EDM + "NavigationProperty")
                             if n.get("Name", "").lower().endswith("kpiid"))
    return {"tables": {t: t in entities for t in TABLES}, "close": close, "kpi_lookups": kpi_lookups}


def check(api: WebApi, out=print) -> int:
    info = parse(api.request("GET", "$metadata").text)
    bad = 0
    for t, ok in info["tables"].items():
        out(f"  table {t:<19} {'present' if ok else 'MISSING'}")
        bad += not ok and t in ("incident", "incidentresolution")
    c = info["close"]
    if c:
        out(f"  action CloseIncident  {'bound' if c['bound'] else 'unbound'}; parameters: "
            f"{', '.join(n for n, _ in c['params'])}")
    else:
        out("  action CloseIncident  MISSING (Learn: it requires Dynamics 365 Customer Service)")
        bad += 1
    out(f"  case KPI lookups      {', '.join(info['kpi_lookups']) or 'none found'}")
    out("OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0
