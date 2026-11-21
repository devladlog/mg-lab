"""Our earlier drafts, as transformations of the real flow definition (for the tests and the CLI)."""
from __future__ import annotations

import copy
import json

from flowkit.lint import definition_of


def _actions(flow):
    return definition_of(flow)["actions"]


def no_pagination(flow: dict) -> dict:
    """Draft 1: List rows with the default settings (no pagination)."""
    f = copy.deepcopy(flow)
    _actions(f)["List_price_rows"].pop("runtimeConfiguration", None)
    return f


def serial_dates(flow: dict) -> dict:
    """Draft 2: DateTime Format left empty, so dates arrive as serial numbers (assumed default)."""
    f = copy.deepcopy(flow)
    _actions(f)["List_price_rows"]["inputs"]["parameters"].pop("dateTimeFormat", None)
    return f


def unencoded_column(flow: dict) -> dict:
    """Draft 3: the Select typed by hand with the column name as it appears in Excel ('Item No.')."""
    f = copy.deepcopy(flow)
    text = json.dumps(_actions(f)["Shape_rows"]).replace("Item No_x002e_", "Item No.")
    _actions(f)["Shape_rows"] = json.loads(text)
    return f


def row_by_row(flow: dict) -> dict:
    """Draft 4: Apply to each valid row: Get a row by SKU, then Update a row or Add a row."""
    f = copy.deepcopy(flow)
    a = _actions(f)
    excel = copy.deepcopy(a["Upsert_catalogue"]["inputs"])
    base = {k: excel["parameters"][k] for k in ("source", "drive", "file")}
    base["table"] = "Catalogue"

    def op(operation, extra):
        inputs = copy.deepcopy(excel)
        inputs["host"]["operationId"] = operation
        inputs["parameters"] = {**base, **extra}
        return inputs

    row = {"SKU": "@items('Each_price')?['sku']", "Description": "@items('Each_price')?['description']",
           "Unit price": "@float(items('Each_price')?['priceText'])", "Valid from": "@items('Each_price')?['validFrom']",
           "Supplier": "Fabrikam", "Source": "@triggerBody()?['{FilenameWithExtension}']"}
    a.pop("Prices_for_script")
    a["Each_price"] = {
        "type": "Foreach", "runAfter": {"Valid_rows": ["Succeeded"]}, "foreach": "@body('Valid_rows')",
        "actions": {
            "Get_a_row": {"type": "OpenApiConnection", "runAfter": {},
                          "inputs": op("GetItem", {"idColumn": "SKU", "id": "@items('Each_price')?['sku']"})},
            "Found": {"type": "If", "runAfter": {"Get_a_row": ["Succeeded", "Failed"]},
                      "expression": {"and": [{"equals": ["@outputs('Get_a_row')?['statusCode']", 200]}]},
                      "actions": {"Update_a_row": {"type": "OpenApiConnection", "runAfter": {},
                                                   "inputs": op("PatchItem", {"idColumn": "SKU", "id": "@items('Each_price')?['sku']", "item": row})}},
                      "else": {"actions": {"Add_a_row": {"type": "OpenApiConnection", "runAfter": {},
                                                         "inputs": op("AddRowV2", {"item": row})}}}},
        },
    }
    a["Upsert_catalogue"] = {"type": "Compose", "runAfter": {"Each_price": ["Succeeded"]},
                             "inputs": {"body": {"result": {"inserted": None, "updated": None, "unchanged": None,
                                                            "duplicatesInFile": None, "duplicateRowsInCatalogue": None,
                                                            "bigChanges": []}}}}
    return f
