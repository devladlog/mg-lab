"""Read the service's own definition of the actions we call from $metadata (CSDL), so nothing is assumed.

Reports, for each action, whether it is bound and to what, and its parameters. If the environment doesn't have
Dynamics 365 Sales installed, the actions are simply missing and `doctor` says so.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List

from .webapi import WebApi

EDM = "{http://docs.oasis-open.org/odata/ns/edm}"
WANTED = ("QualifyLead", "WinOpportunity", "LoseOpportunity")
TABLES = ("lead", "opportunity", "opportunityclose", "account", "contact")


def parse(metadata_xml: str) -> Dict[str, object]:
    root = ET.fromstring(metadata_xml)
    actions: Dict[str, Dict[str, object]] = {}
    entities = set()
    for el in root.iter():
        if el.tag == EDM + "Action" and el.get("Name") in WANTED:
            params = [(p.get("Name"), p.get("Type")) for p in el.findall(EDM + "Parameter")]
            bound = el.get("IsBound") == "true"
            actions[el.get("Name")] = {"bound": bound, "binding": params[0][1] if bound and params else None,
                                       "params": params[1:] if bound else params}
        elif el.tag == EDM + "EntityType":
            entities.add(el.get("Name"))
    return {"actions": actions, "tables": {t: t in entities for t in TABLES}}


def check(api: WebApi, out=print) -> int:
    info = parse(api.request("GET", "$metadata").text)
    bad = 0
    for t, ok in info["tables"].items():
        out(f"  table {t:<17} {'present' if ok else 'MISSING'}")
        bad += not ok
    for name in WANTED:
        a = info["actions"].get(name)
        if not a:
            out(f"  action {name:<15} MISSING (is Dynamics 365 Sales installed in this environment?)")
            bad += 1
            continue
        where = f"bound to {a['binding']}" if a["bound"] else "unbound"
        out(f"  action {name:<15} {where}; parameters: {', '.join(n for n, _ in a['params'])}")
    out("OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0
