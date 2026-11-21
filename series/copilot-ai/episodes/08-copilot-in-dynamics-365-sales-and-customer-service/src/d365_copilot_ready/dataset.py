"""Load Dataverse rows (from Web API JSON files or from a live org) and run the rules over them."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import rules
from .dataverse import DataverseClient

ENTITY_SETS = ["accounts", "opportunities", "opportunityproducts", "quotes", "incidents",
               "annotations", "emails", "knowledgearticles", "languagelocale"]

SELECTS = {
    "accounts": ["accountid", "name", "createdon", "industrycode"],
    "opportunities": ["opportunityid", "name", "statecode", "estimatedvalue", "estimatedclosedate", "actualvalue",
                      "actualclosedate", "budgetamount", "_parentcontactid_value", "_parentaccountid_value"],
    "opportunityproducts": ["opportunityproductid", "_opportunityid_value"],
    "quotes": ["quoteid", "_opportunityid_value"],
    "incidents": ["incidentid", "ticketnumber", "title", "description", "prioritycode", "casetypecode",
                  "_customerid_value", "_productid_value", "_subjectid_value"],
    "annotations": ["annotationid", "notetext", "_objectid_value"],
    "emails": ["activityid", "description", "_regardingobjectid_value"],
    "knowledgearticles": ["knowledgearticleid", "articlepublicnumber", "title", "content", "statecode",
                          "islatestversion", "_languagelocaleid_value"],
    "languagelocale": ["languagelocaleid", "localeid", "code"],
}
FILTERS = {
    "annotations": "objecttypecode eq 'incident'",
    "emails": "_regardingobjectid_value ne null and regardingobjecttypecode eq 'incident'",
}


@dataclass
class Dataset:
    rows: dict[str, list[dict]] = field(default_factory=lambda: {k: [] for k in ENTITY_SETS})


def load_sample(directory: str | Path) -> Dataset:
    """Read <entity set>.json files in the Web API shape: {"value": [ ... ]}."""
    d = Path(directory)
    ds = Dataset()
    for name in ENTITY_SETS:
        p = d / f"{name}.json"
        if p.exists():
            ds.rows[name] = json.loads(p.read_text(encoding="utf-8"))["value"]
    return ds


def load_live(client: DataverseClient) -> Dataset:
    ds = Dataset()
    for name in ENTITY_SETS:
        ds.rows[name] = list(client.get_all(name, SELECTS[name], FILTERS.get(name)))
    return ds


def analyse(ds: Dataset, ui_localeid: int = 1033) -> tuple[list[rules.Finding], dict]:
    r = ds.rows
    products = defaultdict(int)
    for p in r["opportunityproducts"]:
        products[p.get("_opportunityid_value")] += 1
    quotes = defaultdict(int)
    for q in r["quotes"]:
        quotes[q.get("_opportunityid_value")] += 1
    closed = defaultdict(int)
    for o in r["opportunities"]:
        if o.get("statecode") == rules.OPP_WON:
            closed[o.get("_parentaccountid_value")] += 1
    notes = defaultdict(list)
    for n in r["annotations"]:
        notes[n.get("_objectid_value")].append(n.get("notetext") or "")
    mails = defaultdict(list)
    for m in r["emails"]:
        mails[m.get("_regardingobjectid_value")].append(m.get("description") or "")
    locale_of = {x["languagelocaleid"]: x["localeid"] for x in r["languagelocale"]}

    findings: list[rules.Finding] = []
    for o in r["opportunities"]:
        oid = o.get("opportunityid")
        findings += rules.check_opportunity(o, products[oid], quotes[oid])
    for a in r["accounts"]:
        findings += rules.check_account(a, closed[a.get("accountid")])
    for c in r["incidents"]:
        cid = c.get("incidentid")
        findings += rules.check_case(c, notes[cid], mails[cid])
    for k in r["knowledgearticles"]:
        findings += rules.check_article(k, ui_localeid, locale_of)

    usable = [k for k in r["knowledgearticles"] if rules.is_usable(k, ui_localeid, locale_of)]
    summary = {
        "opportunities": len(r["opportunities"]), "accounts": len(r["accounts"]),
        "cases": len(r["incidents"]), "articles": len(r["knowledgearticles"]),
        "articles_usable_for_ui_language": len(usable), "ui_localeid": ui_localeid,
        "errors": sum(f.severity == "error" for f in findings),
        "warnings": sum(f.severity == "warning" for f in findings),
        "info": sum(f.severity == "info" for f in findings),
    }
    return findings, summary
