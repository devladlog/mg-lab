#!/usr/bin/env python3
"""(Episode 4's generator, extended in episode 5 with a Store security page, in episode 7 with a thin report.)

Generate two PBIR report folders from one layout spec (a 12-column grid on a 1280 x 720 page, every visual with a
title, alt text and a tab order that follows the reading order):

  ContosoSales.Report            the model owner's report, bound to the model next to it (byPath), two pages
  thin-report/StoreManagers.Report  a THIN report: no model of its own, a live connection to the semantic model
                                 published in the data workspace (byConnection), one page

The spec below IS the design: change a span or a row here, regenerate, and report-lint checks the result.

Usage:
    python build_report.py           # rewrite both report folders
    python build_report.py --check   # exit 1 if the committed files differ from the spec
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPORT = SRC / "ContosoSales.Report"
THIN = SRC / "thin-report"
THIN_REPORT = THIN / "StoreManagers.Report"
# The live connection of the thin report: the data workspace and the model's name (no IDs: they differ per tenant).
THIN_CONNECTION = ("Data Source=powerbi://api.powerbi.com/v1.0/myorg/Contoso Data (Lab);"
                   "Initial Catalog=ContosoSales")
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

# ---- episode 7: the thin report, built on the shared model only ----------------------------------------
THIN_VISUALS = [
    ("kpiWho", "card", cell(0, 6, ROW1, 112), "Signed in as",
     "The user principal name row-level security evaluates for you.",
     {"Values": [("Sales", "Who Am I", "m")]}, None),
    ("kpiStores", "card", cell(6, 2, ROW1, 112), "Visible stores",
     "Number of stores you can see after row-level security.",
     {"Values": [("Sales", "Visible Stores", "m")]}, None),
    ("kpiSales", "card", cell(8, 2, ROW1, 112), "Sales amount",
     "Total sales amount you can see.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("kpiOrders", "card", cell(10, 2, ROW1, 112), "Orders",
     "Number of distinct orders you can see.",
     {"Values": [("Sales", "Orders", "m")]}, None),
    ("tableStores", "tableEx", cell(0, 6, ROW2, 544), "Your stores",
     "Table of the stores you can see, with country, channel, sales amount and orders.",
     {"Values": [("Store", "Store", "c"), ("Store", "Country", "c"), ("Store", "Channel", "c"),
                 ("Sales", "Sales Amount", "m"), ("Sales", "Orders", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    ("barCategory", "clusteredBarChart", cell(6, 6, ROW2, 544), "Sales amount by category",
     "Sales amount for bikes, accessories and clothing, largest first.",
     {"Category": [("Product", "Category", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
]
THIN_PAGES = [("stores", "My stores", THIN_VISUALS)]


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


def files(pages, reference):
    out = {
        "definition.pbir": {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": reference,
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
            "pageOrder": [p[0] for p in pages], "activePageName": pages[0][0]},
    }
    for page, display, visuals in pages:
        out[f"definition/pages/{page}/page.json"] = {
            "$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": page, "displayName": display, "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W}
        for i, spec in enumerate(visuals):
            out[f"definition/pages/{page}/visuals/{spec[0]}/visual.json"] = visual_json(i, spec)
    rendered = {k: json.dumps(v, indent=2, ensure_ascii=False) + "\n" for k, v in out.items()}
    rendered[f"StaticResources/RegisteredResources/{THEME.name}"] = THEME.read_text(encoding="utf-8")
    return rendered


def pbip(report_folder):
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": report_folder}}],
        "settings": {"enableAutoRecovery": True}}, indent=2) + "\n"


# folder -> (pages, dataset reference) and the extra files that sit beside the report folder
TARGETS = [
    (REPORT, PAGES, {"byPath": {"path": "../ContosoSales.SemanticModel"}}, {}),
    (THIN_REPORT, THIN_PAGES, {"byConnection": {"connectionString": THIN_CONNECTION}},
     {THIN / "StoreManagers.pbip": pbip("StoreManagers.Report")}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = False
    for folder, pages, reference, beside in TARGETS:
        wanted = files(pages, reference)
        existing = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()} if folder.exists() else set()
        stale = sorted(k for k, v in wanted.items()
                       if not (folder / k).exists() or (folder / k).read_text(encoding="utf-8") != v)
        stale += sorted(str(p.name) for p, v in beside.items() if not p.exists() or p.read_text(encoding="utf-8") != v)
        extra = sorted(existing - set(wanted))
        name = folder.relative_to(SRC)
        if a.check:
            for k in stale:
                print(f"{name}: out of date: {k}")
            for k in extra:
                print(f"{name}: not in the spec: {k}")
            bad = bad or bool(stale or extra)
            continue
        if folder.exists():
            shutil.rmtree(folder)
        for k, v in wanted.items():
            (folder / k).parent.mkdir(parents=True, exist_ok=True)
            (folder / k).write_text(v, encoding="utf-8")
        for p, v in beside.items():
            p.write_text(v, encoding="utf-8")
        print(f"wrote {len(wanted)} files ({sum(len(p[2]) for p in pages)} visuals on {len(pages)} page(s)) to {name}")
    if a.check:
        print("reports match the spec" if not bad else "reports differ from the spec")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
