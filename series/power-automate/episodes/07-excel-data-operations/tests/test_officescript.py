"""The Office Script itself: run with Node against an in-memory workbook, checked for Office Scripts' TypeScript rules."""
import json
import re
import shutil
import subprocess

import pytest

from excelfake.connector import RUNNER, run_office_script
from excelfake.workbook import Workbook

from conftest import OFFICESCRIPT, needs_node

SCRIPT = OFFICESCRIPT / "UpsertPrices.ts"
HEADERS = ["SKU", "Description", "Unit price", "Valid from", "Supplier", "Source"]


def wb(rows=None, headers=HEADERS):
    w = Workbook("cat.xlsx")
    w.add_table("Catalogue", headers, rows if rows is not None else [["A-1", "Pens", 2.0, 46174, "Fabrikam", "old.xlsx"]])
    return w


def run(w, prices, supplier="Fabrikam", source="new.xlsx"):
    return run_office_script(RUNNER, "UpsertPrices.ts", w, [prices, supplier, source])


def price(sku="A-1", p=2.2, d="Pens", v="2026-12-01"):
    return {"sku": sku, "description": d, "price": p, "validFrom": v}


@needs_node
def test_an_invalid_row_stops_the_script_before_anything_is_written():
    out = run(wb(), [price("A-2", 3.0), price("A-1", 0)])
    assert out["ok"] is False and "price must be a number greater than zero" in out["error"]
    assert out["writes"] == {"setValues": 0, "addRows": 0}


@needs_node
@pytest.mark.parametrize("w,message", [
    (Workbook("x.xlsx"), "Table 'Catalogue' wasn't found"),
    (wb(headers=["SKU", "Description", "Price", "Valid from", "Supplier", "Source"]), "Column 'Unit price' wasn't found"),
])
def test_a_missing_table_or_column_is_a_clear_error(w, message):
    out = run(w, [price()])
    assert not out["ok"] and message in out["error"]


@needs_node
def test_two_writes_whatever_the_number_of_rows():
    rows = [[f"A-{i}", "x", 1.0, 46174, "Fabrikam", "old.xlsx"] for i in range(2000)]
    prices = [price(f"A-{i}", 1.5, "x") for i in range(2000)] + [price(f"B-{i}", 1.0, "y") for i in range(500)]
    out = run(wb(rows), prices)
    assert out["ok"], out.get("error")
    assert out["result"]["updated"] == 2000 and out["result"]["inserted"] == 500
    assert out["writes"] == {"setValues": 1, "addRows": 1}
    assert len(out["result"]["bigChanges"]) == 2000          # +50 % is over the 20 % default


@needs_node
def test_dates_are_written_as_excel_serial_numbers():
    out = run(wb([]), [price("Y2K", 1.0, v="2000-01-01")])  # Learn: 1 January 2000 is 36526
    assert out["tables"]["Catalogue"]["rows"][0][3] == 36526


@needs_node
def test_no_fetch_in_power_automate():
    js = SCRIPT.read_text(encoding="utf-8")
    assert "fetch(" not in js
    proc = subprocess.run(["node", "-e", "const vm=require('node:vm');console.log(vm.runInNewContext('typeof fetch'))"],
                          capture_output=True, text=True)
    assert proc.stdout.strip() == "undefined"               # the sandbox the runner uses has no fetch


def test_the_script_follows_office_scripts_typescript_rules():
    src = re.sub(r"//.*|/\*[\s\S]*?\*/", "", SCRIPT.read_text(encoding="utf-8"))
    assert not re.search(r":\s*any\b|<any>|as any\b", src), "explicit any isn't allowed"
    assert "eval(" not in src
    for ident in ("Excel", "ExcelScript", "console"):
        assert not re.search(rf"\b(const|let|var|function)\s+{ident}\b", src), f"{ident} is a reserved identifier"
    callbacks = re.findall(r"\.(?:forEach|map|filter|reduce|some|every|find)\(\s*(function\b|[A-Za-z_]\w*\s*\))", src)
    assert callbacks == [], "only arrow functions in array callbacks"
    assert re.search(r"function main\(\s*workbook: ExcelScript\.Workbook", src)


@pytest.mark.skipif(not (OFFICESCRIPT / "node_modules" / "typescript").exists(),
                    reason="run `npm ci` in src/officescript to type-check with TypeScript 4.0.3")
def test_it_compiles_with_the_typescript_version_office_scripts_uses():
    pkg = json.loads((OFFICESCRIPT / "node_modules" / "typescript" / "package.json").read_text())
    assert pkg["version"] == "4.0.3"
    proc = subprocess.run(["node", "node_modules/typescript/bin/tsc", "-p", "tsconfig.json"], cwd=OFFICESCRIPT,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
