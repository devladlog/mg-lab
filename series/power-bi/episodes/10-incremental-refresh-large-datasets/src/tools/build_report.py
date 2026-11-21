#!/usr/bin/env python3
"""Generate the PBIR report folder (one page, 5 visuals, 12-column grid) from the spec below.

The page shows what the partitions really loaded: order lines, orders, sales amount, the newest order and sales by month. Each visual has a title, alt text and a tab order that follows reading order.

    python build_report.py           # rewrite ContosoSalesIR.Report
    python build_report.py --check   # exit 1 if the committed files differ from the spec
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPORT = SRC / "ContosoSalesIR.Report"
THEME = SRC / "themes" / "ContosoBikes.json"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VERSIONS = {"visual": "2.4.0", "report": "3.1.0", "page": "2.1.0"}
PAGE_W, PAGE_H, MARGIN, GUTTER, COLS = 1280, 720, 24, 16, 12
COL_W = (PAGE_W - 2 * MARGIN - (COLS - 1) * GUTTER) // COLS


def cell(col, span, y, height):
    return {"x": MARGIN + col * (COL_W + GUTTER), "y": y, "width": span * (COL_W + GUTTER) - GUTTER, "height": height}


def field(ref):
    table, name, kind = ref
    key = "Measure" if kind == "m" else "Column"
    return {key: {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def literal(value):
    if isinstance(value, bool):
        v = "true" if value else "false"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


VISUALS = [
    ("kpiLines", "card", cell(0, 3, 24, 112), "Order lines",
     "Number of order lines loaded into the model.",
     {"Values": [("Sales", "Order Lines", "m")]}, None),
    ("kpiOrders", "card", cell(3, 3, 24, 112), "Orders",
     "Number of distinct orders loaded into the model.",
     {"Values": [("Sales", "Orders", "m")]}, None),
    ("kpiSales", "card", cell(6, 3, 24, 112), "Sales amount",
     "Total sales amount of the order lines loaded into the model.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("kpiLatest", "card", cell(9, 3, 24, 112), "Latest order",
     "Date and time of the newest order in the model: it moves forward when a refresh loads new days.",
     {"Values": [("Sales", "Latest Order", "m")]}, None),
    ("barMonth", "clusteredColumnChart", cell(0, 12, 152, 400), "Sales amount by month",
     "Monthly sales amount. After the first refresh the model holds the last three whole years and the current year so far.",
     {"Category": [("Sales", "Year Month", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Year Month", "c"), "Ascending")),
]
PAGES = [("overview", "Sales overview", VISUALS)]


def visual_json(index, spec):
    name, vtype, pos, title, alt, roles, sort = spec
    query = {"queryState": {
        role: {"projections": [{"field": field(r), "queryRef": f"{r[0]}.{r[1]}", "nativeQueryRef": r[1]} for r in refs]}
        for role, refs in roles.items()}}
    if sort:
        query["sortDefinition"] = {"sort": [{"field": field(sort[0]), "direction": sort[1]}], "isDefaultSort": False}
    return {
        "$schema": f"{SCHEMA}/visualContainer/{VERSIONS['visual']}/schema.json",
        "name": name,
        "position": {**pos, "z": index * 1000, "tabOrder": index * 1000},
        "visual": {
            "visualType": vtype, "query": query,
            "visualContainerObjects": {
                "title": [{"properties": {"show": literal(True), "text": literal(title)}}],
                "general": [{"properties": {"altText": literal(alt)}}]},
            "drillFilterOtherVisuals": True,
        },
    }


def files():
    out = {
        "definition.pbir": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../ContosoSalesIR.SemanticModel"}}},
        "definition/version.json": {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
        "definition/report.json": {
            "$schema": f"{SCHEMA}/report/{VERSIONS['report']}/schema.json",
            "themeCollection": {"customTheme": {
                "name": THEME.name, "reportVersionAtImport": VERSIONS, "type": "RegisteredResources"}},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                                  "items": [{"name": THEME.name, "path": THEME.name, "type": "CustomTheme"}]}]},
        "definition/pages/pages.json": {
            "$schema": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]},
    }
    for page, display, visuals in PAGES:
        out[f"definition/pages/{page}/page.json"] = {
            "$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": page, "displayName": display, "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W}
        for i, spec in enumerate(visuals):
            out[f"definition/pages/{page}/visuals/{spec[0]}/visual.json"] = visual_json(i, spec)
    rendered = {k: json.dumps(v, indent=2, ensure_ascii=False) + "\n" for k, v in out.items()}
    rendered[f"StaticResources/RegisteredResources/{THEME.name}"] = THEME.read_text(encoding="utf-8")
    return rendered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    wanted = files()
    existing = {str(p.relative_to(REPORT)) for p in REPORT.rglob("*") if p.is_file()} if REPORT.exists() else set()
    stale = sorted(k for k, v in wanted.items() if not (REPORT / k).exists() or (REPORT / k).read_text(encoding="utf-8") != v)
    extra = sorted(existing - set(wanted))
    if a.check:
        for k in stale:
            print(f"out of date: {k}")
        for k in extra:
            print(f"not in the spec: {k}")
        print("report matches the spec" if not (stale or extra) else "report differs from the spec")
        sys.exit(1 if (stale or extra) else 0)
    if REPORT.exists():
        shutil.rmtree(REPORT)
    for k, v in wanted.items():
        (REPORT / k).parent.mkdir(parents=True, exist_ok=True)
        (REPORT / k).write_text(v, encoding="utf-8")
    print(f"wrote {len(wanted)} files ({sum(len(p[2]) for p in PAGES)} visuals on {len(PAGES)} page) to {REPORT.name}")


if __name__ == "__main__":
    main()
