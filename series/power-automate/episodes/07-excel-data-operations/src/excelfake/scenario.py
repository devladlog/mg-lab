"""Contoso purchasing: Fabrikam's December price list goes into the purchasing catalogue.

The supplier file "Fabrikam price list 2026-12.xlsx" has a table "Prices" with 400 rows:
- FAB-0001 .. FAB-0395, one row each (395 rows);
- FAB-0042 a second time, with a corrected price (the last row wins);
- four bad rows: no item number, price "n/a", price typed as text "12,50", price -3.20.

"Purchasing catalogue.xlsx" has a table "Catalogue" with FAB-0001 .. FAB-0380 (FAB-0007 pasted twice).
Of those 380: every fourth price is unchanged, the rest go up 3 %, and three change a lot
(FAB-0100 +35 %, FAB-0200 -40 %, FAB-0300 +25 %). FAB-0381 .. FAB-0395 are new.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from flowkit import RunResult, Simulator, load_flow
from flowkit.lint import iter_actions, definition_of

from .connector import Excel, ExcelError
from .workbook import ExcelDate, Workbook

ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = next((ROOT / "solution" / "Workflows").glob("Supplierpricelistimport-*.json"))
PRICE_FILE = "Fabrikam price list 2026-12.xlsx"
CATALOGUE_FILE = "Purchasing catalogue.xlsx"
PRICE_FILE_ID = "%252fPrice%2520lists%252fFabrikam%2520price%2520list%25202026-12.xlsx"
CATALOGUE_FILE_ID = "Purchasing catalogue.xlsx"   # path from the drive (Learn: File parameter options)
NOW = datetime(2026, 12, 1, 7, 45, tzinfo=timezone.utc)

PRODUCTS = ["Ballpoint pens, blue, box of 50", "A4 copy paper 80 g, 500 sheets", "Stapler, desktop",
            "Staples 26/6, box of 5000", "Sticky notes 76 x 76 mm, pack of 12", "Lever arch file A4",
            "Whiteboard markers, assorted, 4", "Envelopes C5, box of 500", "Desk organiser, black",
            "USB-C cable 2 m", "Laptop stand, aluminium", "Wireless mouse"]
SUPPLIER_HEADERS = ["Item No.", "Description", "Unit price", "Valid from"]
CATALOGUE_HEADERS = ["SKU", "Description", "Unit price", "Valid from", "Supplier", "Source"]
VALID_FROM = date(2026, 12, 1)
BIG = {100: 1.35, 200: 0.60, 300: 1.25}


def sku(i: int) -> str:
    return f"FAB-{i:04d}"


def old_price(i: int) -> float:
    return round(1.5 + (i * 7 % 90) * 0.35, 2)


def new_price(i: int) -> float:
    if i in BIG:
        return round(old_price(i) * BIG[i], 2)
    if i % 4 == 0:
        return old_price(i)
    return round(old_price(i) * 1.03, 2)


def description(i: int) -> str:
    return PRODUCTS[i % len(PRODUCTS)]


def price_list(rows: int = 395) -> Workbook:
    data = [[sku(i), description(i), new_price(i), ExcelDate.of(VALID_FROM)] for i in range(1, rows + 1)]
    data.append([sku(42), description(42), round(new_price(42) - 0.10, 2), ExcelDate.of(VALID_FROM)])
    data += [
        [None, "Desk lamp, LED", 24.9, ExcelDate.of(VALID_FROM)],
        [sku(396), "Monitor arm, single", "n/a", ExcelDate.of(VALID_FROM)],
        [sku(397), "Headset, USB", "12,50", ExcelDate.of(VALID_FROM)],
        [sku(398), "Cable ties, pack of 100", -3.2, ExcelDate.of(VALID_FROM)],
    ]
    wb = Workbook(PRICE_FILE)
    wb.add_table("Prices", SUPPLIER_HEADERS, data)
    return wb


def big_price_list(rows: int) -> Workbook:
    wb = Workbook("Fabrikam full catalogue.xlsx")
    wb.add_table("Prices", SUPPLIER_HEADERS,
                 [[f"FAB-{i:05d}", "Item", 1.0 + i % 50, ExcelDate.of(VALID_FROM)] for i in range(1, rows + 1)])
    return wb


def catalogue() -> Workbook:
    rows = [[sku(i), description(i), old_price(i), ExcelDate.of(date(2026, 6, 1)), "Fabrikam", "Fabrikam price list 2026-06.xlsx"]
            for i in range(1, 381)]
    rows.insert(7, list(rows[6]))  # FAB-0007 pasted twice by hand
    wb = Workbook(CATALOGUE_FILE)
    wb.add_table("Catalogue", CATALOGUE_HEADERS, rows)
    return wb


def trigger_body(name: str = PRICE_FILE, file_id: str = PRICE_FILE_ID) -> dict:
    """SharePoint 'When a file is created (properties only)' item for the Price lists library."""
    return {
        "ID": 17, "{Name}": name.rsplit(".", 1)[0], "{FilenameWithExtension}": name,
        "{Identifier}": file_id, "{Path}": "Price lists/", "{IsFolder}": False,
        "{Link}": f"https://contoso.sharepoint.com/sites/Purchasing/Price%20lists/{name.replace(' ', '%20')}",
        "Author": {"DisplayName": "Jordan Demo", "Email": "jordan.demo@contoso.com"},
    }


@dataclass
class Outcome:
    run: RunResult
    excel: Excel
    files: dict = field(default_factory=dict)   # SharePoint files created: path -> content
    mail: list = field(default_factory=list)

    @property
    def result(self) -> dict | None:
        res = self.run.actions.get("Upsert_catalogue")
        return (res.outputs or {}).get("body", {}).get("result") if res and res.outputs else None

    def catalogue_rows(self) -> list[list]:
        return self.excel.files[CATALOGUE_FILE_ID].tables["Catalogue"].rows


def _find(flow: dict, name: str) -> dict:
    for n, a, *_ in iter_actions(definition_of(flow).get("actions", {})):
        if n == name:
            return a
    raise KeyError(name)


def mocks_for(flow: dict, excel: Excel, files: dict, mail: list) -> dict:
    """One mock per connector action, keyed by action name, routed by operation id."""
    def excel_op(name, action):
        op = action["inputs"]["host"]["operationId"]
        threshold = ((action.get("runtimeConfiguration") or {}).get("paginationPolicy") or {}).get("minimumItemCount")

        def call(inputs):
            p = inputs["parameters"]
            try:
                body = {"GetItems": lambda: excel.get_items(p, threshold),
                        "GetItem": lambda: excel.get_item(p),
                        "PatchItem": lambda: excel.patch_item(p),
                        "AddRowV2": lambda: excel.add_row(p),
                        "RunScriptProdV2": lambda: excel.run_script(p)}[op]()
            except ExcelError as e:
                return {"status": "Failed", "statusCode": e.status, "body": {"message": e.message}, "error": e.message}
            return {"status": "Succeeded", "body": body}
        return call

    def create_file(inputs):
        p = inputs["parameters"]
        files[f"{p['folderPath'].rstrip('/')}/{p['name']}"] = p["body"]
        return {"status": "Succeeded", "body": {"Name": p["name"]}}

    def send_mail(inputs):
        mail.append(inputs["parameters"])
        return {"status": "Succeeded", "body": None}

    mocks = {}
    for n, a, *_ in iter_actions(definition_of(flow).get("actions", {})):
        host = ((a.get("inputs") or {}).get("host") or {}) if isinstance(a.get("inputs"), dict) else {}
        api = str(host.get("apiId", ""))
        if api.endswith("shared_excelonlinebusiness"):
            mocks[n] = excel_op(n, a)
        elif host.get("operationId") == "CreateFile":
            mocks[n] = create_file
        elif host.get("operationId") == "SendEmailV2":
            mocks[n] = send_mail
    return mocks


def run_import(flow: dict | None = None, price_wb: Workbook | None = None, catalogue_wb: Workbook | None = None,
               name: str = PRICE_FILE) -> Outcome:
    flow = flow or load_flow(FLOW_PATH)
    excel = Excel()
    excel.put(PRICE_FILE_ID, price_wb or price_list())
    excel.put(CATALOGUE_FILE_ID, catalogue_wb or catalogue())
    files, mail = {}, []
    sim = Simulator(flow, mocks=mocks_for(flow, excel, files, mail), now=NOW)
    run = sim.run(trigger_body(name))
    return Outcome(run, excel, files, mail)


def describe(o: Outcome) -> str:
    lines = [f"run {o.run.status}" + (f"  {o.run.terminate_error}" if o.run.terminate_error else "")]
    listed = o.run.actions.get("List_price_rows")
    if listed and listed.outputs:
        lines.append(f"rows read from the price list: {len((listed.outputs.get('body') or {}).get('value', []))}")
    rej = o.run.actions.get("Rejected_rows")
    if rej and rej.outputs:
        lines.append(f"rejected by the flow: {len(rej.outputs['body'])}")
        for r in rej.outputs["body"]:
            lines.append(f"  {r['sku'] or '(no item number)':<17} {r['priceText']:<6} {r['problem']}")
    if o.result and o.result.get('inserted') is not None:
        r = o.result
        lines.append(f"script: {r['inserted']} new, {r['updated']} updated, {r['unchanged']} unchanged, "
                     f"{r['duplicatesInFile']} duplicate in file, {r['duplicateRowsInCatalogue']} duplicate catalogue row")
        for c in r["bigChanges"]:
            lines.append(f"  check {c['sku']}: {c['oldPrice']} -> {c['newPrice']} ({c['changePercent']:+} %)")
    for n, res in o.run.actions.items():
        if res.status == "Failed" and res.error:
            lines.append(f"  {n}: {res.error}")
    lines.append(f"Excel connector calls: {len(o.excel.calls)} (at 100 per minute per connection: "
                 f"at least {o.excel.minimum_minutes} min)   Power Platform requests: {o.run.executions}")
    for path in o.files:
        lines.append(f"file created: {path}")
    for m in o.mail:
        lines.append(f"email: {m.get('emailMessage/Subject')}")
    return "\n".join(lines)
