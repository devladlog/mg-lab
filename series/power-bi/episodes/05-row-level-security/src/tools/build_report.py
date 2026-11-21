#!/usr/bin/env python3
"""(Episode 4's generator, extended in episode 5 with a Store security page and a Sales by store bar.)

Generate the PBIR report folder (ContosoSales.Report) from one layout spec: a 12-column grid on a
1280 x 720 page, every visual with a title, alt text and a tab order that follows the reading order.

The spec below IS the design: change a span or a row here, regenerate, and report-lint checks the result.

Usage:
    python build_report.py           # rewrite ContosoSales.Report
    python build_report.py --check   # exit 1 if the committed files differ from the spec
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPORT = SRC / "ContosoSales.Report"
THEME = SRC / "themes" / "ContosoBikes.json"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VERSIONS = {"visual": "2.4.0", "report": "3.1.0", "page": "2.1.0"}

# ---- the grid: 8 px base unit, 24 px margins, 12 columns of 88 px with 16 px gutters ----------------
PAGE_W, PAGE_H, MARGIN, GUTTER, COLS = 1280, 720, 24, 16, 12
COL_W = (PAGE_W - 2 * MARGIN - (COLS - 1) * GUTTER) // COLS          # 88


def cell(col, span, y, height):
    return {"x": MARGIN + col * (COL_W + GUTTER), "y": y, "width": span * (COL_W + GUTTER) - GUTTER, "height": height}


def measure(table, name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def column(table, name):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def literal(value):
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)):
        v = f"{value}D"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


# ---- the page: (name, visualType, grid cell, title, alt text, {role: [fields]}, sort) -------------------
ROW1, ROW2, ROW3 = 24, 152, 432
VISUALS = [
    ("kpiSales", "card", cell(0, 3, ROW1, 112), "Sales amount",
     "Total sales amount for the selected years.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("kpiGrowth", "card", cell(3, 3, ROW1, 112), "Sales growth vs prior year",
     "Year over year change in sales amount. Blank when the period has no sales.",
     {"Values": [("Sales", "Sales YoY %", "m")]}, None),
    ("kpiOrders", "card", cell(6, 3, ROW1, 112), "Orders",
     "Number of distinct orders for the selected years.",
     {"Values": [("Sales", "Orders", "m")]}, None),
    ("slicerYear", "slicer", cell(9, 3, ROW1, 112), "Year",
     "Year slicer. Filters every visual on the page.",
     {"Values": [("Date", "Year", "c")]}, None),
    ("trendSales", "lineChart", cell(0, 8, ROW2, 264), "Sales amount and prior year by month",
     "Monthly sales amount compared with the same month of the prior year.",
     {"Category": [("Date", "Year Month", "c")], "Y": [("Sales", "Sales Amount", "m"), ("Sales", "Sales PY", "m")]},
     (("Date", "Year Month", "c"), "Ascending")),
    ("barCategory", "clusteredBarChart", cell(8, 4, ROW2, 264), "Sales amount by category",
     "Sales amount for bikes, accessories and clothing, largest first.",
     {"Category": [("Product", "Category", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    ("tableProducts", "tableEx", cell(0, 6, ROW3, 264), "Products ranked inside their category",
     "Table of products with sales amount, rank inside the category and share of the category.",
     {"Values": [("Product", "Category", "c"), ("Product", "Product", "c"), ("Sales", "Sales Amount", "m"),
                 ("Sales", "Product Rank", "m"), ("Sales", "% of Category", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    # Episode 5: the cell episode 4 kept free for the custom visual now shows the store split RLS acts on.
    ("barStore", "clusteredBarChart", cell(6, 6, ROW3, 264), "Sales amount by store",
     "Sales amount per store, largest first. Row-level security limits the stores you see.",
     {"Category": [("Store", "Store", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
]

# ---- episode 5: a page that shows what row-level security leaves you ----------------------------------
SECURITY = [
    ("kpiWho", "card", cell(0, 6, ROW1, 112), "Signed in as",
     "The user principal name row-level security evaluates for you.",
     {"Values": [("Sales", "Who Am I", "m")]}, None),
    ("kpiStores", "card", cell(6, 2, ROW1, 112), "Visible stores",
     "Number of stores you can see after row-level security.",
     {"Values": [("Sales", "Visible Stores", "m")]}, None),
    ("kpiCustomers", "card", cell(8, 2, ROW1, 112), "Visible customers",
     "Number of customers you can see after row-level security.",
     {"Values": [("Sales", "Visible Customers", "m")]}, None),
    ("kpiSalesSecurity", "card", cell(10, 2, ROW1, 112), "Sales amount",
     "Total sales amount you can see.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("tableStores", "tableEx", cell(0, 6, ROW2, 544), "Stores you can see",
     "Table of the stores row-level security leaves you, with country, channel, sales amount and orders.",
     {"Values": [("Store", "Store", "c"), ("Store", "Country", "c"), ("Store", "Channel", "c"),
                 ("Sales", "Sales Amount", "m"), ("Sales", "Orders", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    ("slicerCustomer", "slicer", cell(6, 6, ROW2, 544), "Customers you can see",
     "List of customer names left after row-level security. It should only show customers of your stores.",
     {"Values": [("Customer", "Customer", "c")]}, None),
]

PAGES = [("overview", "Sales overview", VISUALS), ("security", "Store security", SECURITY)]


def field(ref):
    table, name, kind = ref
    return measure(table, name) if kind == "m" else column(table, name)


def visual_json(index, spec):
    name, vtype, pos, title, alt, roles, sort = spec
    query = {"queryState": {
        role: {"projections": [{"field": field(r), "queryRef": f"{r[0]}.{r[1]}", "nativeQueryRef": r[1]}
                               for r in refs]}
        for role, refs in roles.items()}}
    if sort:
        query["sortDefinition"] = {"sort": [{"field": field(sort[0]), "direction": sort[1]}], "isDefaultSort": False}
    return {
        "$schema": f"{SCHEMA}/visualContainer/{VERSIONS['visual']}/schema.json",
        "name": name,
        "position": {**pos, "z": index * 1000, "tabOrder": index * 1000},
        "visual": {
            "visualType": vtype,
            "query": query,
            "visualContainerObjects": {
                "title": [{"properties": {"show": literal(True), "text": literal(title)}}],
                "general": [{"properties": {"altText": literal(alt)}}],
            },
            "drillFilterOtherVisuals": True,
        },
    }


def files():
    out = {
        "definition.pbir": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../ContosoSales.SemanticModel"}},
        },
        "definition/version.json": {
            "$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
        "definition/report.json": {
            "$schema": f"{SCHEMA}/report/{VERSIONS['report']}/schema.json",
            "themeCollection": {"customTheme": {
                "name": THEME.name, "reportVersionAtImport": VERSIONS, "type": "RegisteredResources"}},
            "resourcePackages": [{
                "name": "RegisteredResources", "type": "RegisteredResources",
                "items": [{"name": THEME.name, "path": THEME.name, "type": "CustomTheme"}]}],
        },
        "definition/pages/pages.json": {
            "$schema": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
            "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]},
    }
    for page, display, visuals in PAGES:
        out[f"definition/pages/{page}/page.json"] = {
            "$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": page, "displayName": display, "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W}
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
    stale = sorted(k for k, v in wanted.items()
                   if not (REPORT / k).exists() or (REPORT / k).read_text(encoding="utf-8") != v)
    extra = sorted(existing - set(wanted))
    if a.check:
        for k in stale:
            print(f"out of date: {k}")
        for k in extra:
            print(f"not in the spec: {k}")
        print("report matches the spec" if not (stale or extra) else "report differs from the spec")
        sys.exit(1 if stale or extra else 0)
    if REPORT.exists():
        shutil.rmtree(REPORT)
    for k, v in wanted.items():
        (REPORT / k).parent.mkdir(parents=True, exist_ok=True)
        (REPORT / k).write_text(v, encoding="utf-8")
    print(f"wrote {len(wanted)} files ({sum(len(p[2]) for p in PAGES)} visuals on {len(PAGES)} pages) to {REPORT.relative_to(SRC)}")


if __name__ == "__main__":
    main()
