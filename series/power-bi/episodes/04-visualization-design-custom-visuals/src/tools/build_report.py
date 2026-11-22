#!/usr/bin/env python3
"""Generate the PBIR report folder (ContosoSales.Report) from one layout spec: a 12-column grid on a
1280 x 720 page, every visual with a title, alt text and a tab order that follows the reading order.
A second page, Showcase, uses the same 1280 x 720 canvas on a 24 px grid: a headline, Year tiles, four KPI
cards, the Target bullet custom visual as the hero, sales against the prior year by month, categories and a
compact top-products table. No colour is set in the page files: everything visual comes from the report
theme, so importing src/themes/ContosoNightRide.json in Desktop restyles the page without touching it.

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
TARGET_BULLET = "contosoTargetBullet7C1E2A9B4D5F4E0A8B3C6D2E1F0A9B8C"   # pbiviz.json visual.guid
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
]
# cell(6, 6, ROW3, 264) is left free for the Target bullet custom visual (added in Desktop, see demo.md)


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


# ---- the Showcase page: same 1280 x 720 canvas, every x / y / width / height a multiple of 24 ------------------
# 4 columns of 288 px with 24 px gutters from x = 24: 24 + 4 * 288 + 3 * 24 = 1248 (1280 isn't a multiple of 24,
# so the right margin is 32). Rows: headline 96, KPI cards 96, hero 216, bottom 192, 24 px apart (= 720).
SC_UNIT, SC_COL, SC_COLS = 24, 288, 4
SC_W, SC_H = PAGE_W, PAGE_H


def sc_cell(col, span, y, height):
    return {"x": SC_UNIT + col * (SC_COL + SC_UNIT), "y": y,
            "width": span * (SC_COL + SC_UNIT) - SC_UNIT, "height": height}


SC_HEAD, SC_KPI, SC_HERO, SC_BOTTOM = 24, 144, 264, 504
HEADLINE = "Sales up 8.1% in 2025 \u2014 Bikes carry the climb"      # tests/test_expected.py checks the claim
CREDIT = "Contoso Bikes \u00b7 fictional data \u00b7 DEVLADLOG Power BI #4 \u00b7 MG Lab"
HIDE_CATEGORY_LABEL = {"categoryLabels": [{"properties": {"show": literal(False)}}]}
SHOWCASE = [
    # textbox paragraphs as Desktop writes them in PBIR; no colour, so the theme's text colour applies
    dict(name="scHeader", type="textbox", pos=sc_cell(0, 3, SC_HEAD, 96), title="Headline", show_title=False,
         alt=HEADLINE + ". " + CREDIT + ".",
         objects={"general": [{"properties": {"paragraphs": [
             {"textRuns": [{"value": HEADLINE, "textStyle": {"fontFamily": "Georgia", "fontSize": "20pt"}}]},
             {"textRuns": [{"value": CREDIT, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "9pt"}}]},
         ]}}]}),
    dict(name="scYear", type="slicer", pos=sc_cell(3, 1, SC_HEAD, 96), title="Year", show_title=False,
         alt="Year slicer as tiles. Filters every visual on the page.",
         roles={"Values": [("Date", "Year", "c")]},
         objects={"data": [{"properties": {"mode": literal("HorizontalList")}}],     # theme schema: "Tile"
                  "header": [{"properties": {"show": literal(False)}}]}),
    dict(name="scSales", type="card", pos=sc_cell(0, 1, SC_KPI, 96), title="Sales amount",
         alt="Total sales amount for the selected years.",
         roles={"Values": [("Sales", "Sales Amount", "m")]}, objects=HIDE_CATEGORY_LABEL),
    dict(name="scGrowth", type="card", pos=sc_cell(1, 1, SC_KPI, 96), title="Growth vs prior year",
         alt="Year over year change in sales amount. Blank when the period has no sales.",
         roles={"Values": [("Sales", "Sales YoY %", "m")]}, objects=HIDE_CATEGORY_LABEL),
    dict(name="scOrders", type="card", pos=sc_cell(2, 1, SC_KPI, 96), title="Orders",
         alt="Number of distinct orders for the selected years.",
         roles={"Values": [("Sales", "Orders", "m")]}, objects=HIDE_CATEGORY_LABEL),
    dict(name="scUnits", type="card", pos=sc_cell(3, 1, SC_KPI, 96), title="Units sold",
         alt="Number of units sold for the selected years.",
         roles={"Values": [("Sales", "Units", "m")]}, objects=HIDE_CATEGORY_LABEL),
    dict(name="scBullet", type=TARGET_BULLET, pos=sc_cell(0, 2, SC_HERO, 216),
         title="Sales vs prior year by category",
         subtitle="Bar = sales, tick = prior year \u00b7 \u25b2 above \u00b7 \u25cf within 5% \u00b7 \u25bc below",
         alt="Bullet per category: sales against the prior year, with marker and percentage.",
         roles={"category": [("Product", "Category", "c")], "actual": [("Sales", "Sales Amount", "m")],
                "target": [("Sales", "Sales PY", "m")]}),
    dict(name="scTrend", type="lineChart", pos=sc_cell(2, 2, SC_HERO, 216), title="Sales vs prior year by month",
         subtitle="Sales Amount and Sales PY",
         alt="Monthly sales amount compared with the same month of the prior year.",
         roles={"Category": [("Date", "Month", "c")],
                "Y": [("Sales", "Sales Amount", "m"), ("Sales", "Sales PY", "m")]},
         sort=(("Date", "Month", "c"), "Ascending")),
    dict(name="scCategory", type="clusteredBarChart", pos=sc_cell(0, 1, SC_BOTTOM, 192), title="Sales by category",
         subtitle="Largest first", alt="Sales amount for bikes, accessories and clothing, largest first.",
         roles={"Category": [("Product", "Category", "c")], "Y": [("Sales", "Sales Amount", "m")]},
         sort=(("Sales", "Sales Amount", "m"), "Descending")),
    dict(name="scProducts", type="tableEx", pos=sc_cell(1, 3, SC_BOTTOM, 192), title="Top products",
         subtitle="By sales amount, with the rank inside their category",
         alt="Table of products by sales amount, largest first, with category and rank inside the category.",
         roles={"Values": [("Product", "Product", "c"), ("Product", "Category", "c"), ("Sales", "Sales Amount", "m"),
                           ("Sales", "Product Rank", "m")]},
         sort=(("Sales", "Sales Amount", "m"), "Descending")),
]


def showcase_visual_json(index, spec):
    visual = {"visualType": spec["type"]}
    if spec.get("roles"):
        query = {"queryState": {
            role: {"projections": [{"field": field(r), "queryRef": f"{r[0]}.{r[1]}", "nativeQueryRef": r[1]}
                                   for r in refs]}
            for role, refs in spec["roles"].items()}}
        if spec.get("sort"):
            query["sortDefinition"] = {"sort": [{"field": field(spec["sort"][0]), "direction": spec["sort"][1]}],
                                       "isDefaultSort": False}
        visual["query"] = query
    if spec.get("objects"):
        visual["objects"] = spec["objects"]
    container = {"title": [{"properties": {"show": literal(spec.get("show_title", True)), "text": literal(spec["title"])}}]}
    if spec.get("subtitle"):
        container["subTitle"] = [{"properties": {"show": literal(True), "text": literal(spec["subtitle"])}}]
    container["general"] = [{"properties": {"altText": literal(spec["alt"])}}]
    visual["visualContainerObjects"] = container
    visual["drillFilterOtherVisuals"] = True
    return {
        "$schema": f"{SCHEMA}/visualContainer/{VERSIONS['visual']}/schema.json",
        "name": spec["name"],
        "position": {**spec["pos"], "z": index * 1000, "tabOrder": index * 1000},
        "visual": visual,
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
            "pageOrder": ["overview", "showcase"], "activePageName": "overview"},
        "definition/pages/overview/page.json": {
            "$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": "overview", "displayName": "Sales overview", "displayOption": "FitToPage",
            "height": PAGE_H, "width": PAGE_W},
        "definition/pages/showcase/page.json": {
            "$schema": f"{SCHEMA}/page/{VERSIONS['page']}/schema.json",
            "name": "showcase", "displayName": "Showcase", "displayOption": "FitToPage",
            "height": SC_H, "width": SC_W},
    }
    for i, spec in enumerate(VISUALS):
        out[f"definition/pages/overview/visuals/{spec[0]}/visual.json"] = visual_json(i, spec)
    for i, spec in enumerate(SHOWCASE):
        out[f"definition/pages/showcase/visuals/{spec['name']}/visual.json"] = showcase_visual_json(i, spec)
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
    print(f"wrote {len(wanted)} files ({len(VISUALS)} + {len(SHOWCASE)} visuals) to {REPORT.relative_to(SRC)}")


if __name__ == "__main__":
    main()
