#!/usr/bin/env python3
"""(The generator of episodes 4-7, now producing the two reports of the performance episode.)

  ContosoPerf.Before.Report   one executive page with 13 visuals, including a table of every order line
  ContosoPerf.After.Report    the same questions on a 7-visual executive page, the order lines on their own page

Both are PBIR folders on a 12-column grid (1280 x 720), every visual with a title, alt text and a tab order that
follows the reading order. The spec below IS the design.

    python build_report.py           # rewrite both report folders
    python build_report.py --check   # exit 1 if the committed files differ from the spec
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
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


# ---- BEFORE: everything on one page -------------------------------------------------------------------
R1, R2, R3, R4 = 24, 152, 248, 464
BEFORE_VISUALS = [
    ("kpiSales", "card", cell(0, 2, R1, 112), "Sales amount", "Total sales amount for the selected filters.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("kpiMargin", "card", cell(2, 2, R1, 112), "Margin percent", "Margin as a share of sales amount.",
     {"Values": [("Sales", "Margin %", "m")]}, None),
    ("kpiGrowth", "card", cell(4, 2, R1, 112), "Growth vs prior year", "Year over year change in sales amount.",
     {"Values": [("Sales", "Sales YoY %", "m")]}, None),
    ("kpiOrders", "card", cell(6, 2, R1, 112), "Orders", "Number of distinct orders.",
     {"Values": [("Sales", "Orders", "m")]}, None),
    ("kpiUnits", "card", cell(8, 2, R1, 112), "Units", "Units sold.",
     {"Values": [("Sales", "Units", "m")]}, None),
    ("kpiOnline", "card", cell(10, 2, R1, 112), "Online sales", "Sales amount of the online shop.",
     {"Values": [("Sales", "Online Sales", "m")]}, None),
    ("slicerYear", "slicer", cell(0, 4, R2, 80), "Year", "Year slicer. Filters every visual on the page.",
     {"Values": [("Date", "Year", "c")]}, None),
    ("slicerCategory", "slicer", cell(4, 4, R2, 80), "Category", "Product category slicer.",
     {"Values": [("Product", "Category", "c")]}, None),
    ("slicerStore", "slicer", cell(8, 4, R2, 80), "Store", "Store slicer.",
     {"Values": [("Store", "Store", "c")]}, None),
    ("trendSales", "lineChart", cell(0, 6, R3, 200), "Sales amount by month", "Monthly sales amount.",
     {"Category": [("Date", "Year Month", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Date", "Year Month", "c"), "Ascending")),
    ("barCategory", "clusteredBarChart", cell(6, 3, R3, 200), "Sales amount by category",
     "Sales amount for bikes, accessories and clothing, largest first.",
     {"Category": [("Product", "Category", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    ("barStore", "clusteredBarChart", cell(9, 3, R3, 200), "Sales amount by store",
     "Sales amount per store, largest first.",
     {"Category": [("Store", "Store", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    # the visual that makes the page slow: every order line, no Top N filter
    ("tableLines", "tableEx", cell(0, 12, R4, 232), "Every order line",
     "Table of every order line with timestamp, customer, product, store and sales amount.",
     {"Values": [("Sales", "Order Number", "c"), ("Sales", "Order Timestamp", "c"), ("Customer", "Customer", "c"),
                 ("Product", "Product", "c"), ("Store", "Store", "c"), ("Sales", "Sales Amount", "m")]}, None),
]
BEFORE_PAGES = [("executive", "Executive", BEFORE_VISUALS)]

# ---- AFTER: the same questions, fewer visuals; the detail moved to its own page -------------------------
AFTER_VISUALS = [
    ("kpiSales", "card", cell(0, 3, R1, 112), "Sales amount", "Total sales amount for the selected filters.",
     {"Values": [("Sales", "Sales Amount", "m")]}, None),
    ("kpiMargin", "card", cell(3, 3, R1, 112), "Margin percent", "Margin as a share of sales amount.",
     {"Values": [("Sales", "Margin %", "m")]}, None),
    ("kpiGrowth", "card", cell(6, 3, R1, 112), "Growth vs prior year", "Year over year change in sales amount.",
     {"Values": [("Sales", "Sales YoY %", "m")]}, None),
    ("slicerYear", "slicer", cell(9, 3, R1, 112), "Year", "Year slicer. Filters every visual on the page.",
     {"Values": [("Date", "Year", "c")]}, None),
    ("trendSales", "lineChart", cell(0, 6, R2, 264), "Sales amount by month", "Monthly sales amount.",
     {"Category": [("Date", "Year Month", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Date", "Year Month", "c"), "Ascending")),
    ("barCategory", "clusteredBarChart", cell(6, 3, R2, 264), "Sales amount by category",
     "Sales amount for bikes, accessories and clothing, largest first.",
     {"Category": [("Product", "Category", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
    ("barStore", "clusteredBarChart", cell(9, 3, R2, 264), "Sales amount by store",
     "Sales amount per store, largest first.",
     {"Category": [("Store", "Store", "c")], "Y": [("Sales", "Sales Amount", "m")]},
     (("Sales", "Sales Amount", "m"), "Descending")),
]
LINES_VISUALS = [
    ("slicerStore", "slicer", cell(0, 4, R1, 80), "Store", "Store slicer. Narrows the order lines.",
     {"Values": [("Store", "Store", "c")]}, None),
    ("tableLines", "tableEx", cell(0, 12, 120, 576), "Order lines of the selected store",
     "Table of order lines with number, date, customer, product and sales amount. Pick a store first.",
     {"Values": [("Sales", "Order Number", "c"), ("Date", "Date", "c"), ("Customer", "Customer", "c"),
                 ("Product", "Product", "c"), ("Sales", "Sales Amount", "m")]}, None),
]
AFTER_PAGES = [("executive", "Executive", AFTER_VISUALS), ("lines", "Order lines", LINES_VISUALS)]


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


TARGETS = [
    (SRC / "ContosoPerf.Before.Report", BEFORE_PAGES, {"byPath": {"path": "../ContosoPerf.Before.SemanticModel"}}),
    (SRC / "ContosoPerf.After.Report", AFTER_PAGES, {"byPath": {"path": "../ContosoPerf.After.SemanticModel"}}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = False
    for folder, pages, reference in TARGETS:
        beside = {}
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
