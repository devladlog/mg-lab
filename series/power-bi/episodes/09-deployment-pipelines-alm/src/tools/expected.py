#!/usr/bin/env python3
"""Expected card values of each stage, computed from the CSV files the way the model's M does.

Mirror of the Sales partition: read every CSV of the stage's folder (semicolons, decimal comma, TOTAL footer), sort by
file name descending, keep the first row of each (OrderNumber, LineNumber), then Sales Amount = sum(Quantity x UnitPrice),
Orders = distinct OrderNumber, Order Lines = rows. The M itself never ran here; this is the number to compare against on
the recording day.

    python expected.py [data/ContosoBikesData]       # prints the three stages
"""
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "ContosoBikesData"
# parameter ExportsFolder per stage (the deployment rules of Test and Production; Development keeps the saved value)
STAGES = {"DEV": "exports-sample", "TEST": "exports", "PROD": "exports"}


def stage_values(folder: Path) -> dict:
    rows = {}
    for f in sorted(folder.glob("*.csv"), key=lambda p: p.name, reverse=True):
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                if r["OrderNumber"] == "TOTAL":
                    continue
                rows.setdefault((r["OrderNumber"], r["LineNumber"]), r)
    amount = sum(Decimal(int(r["Quantity"])) * Decimal(r["UnitPrice"].replace(",", ".")) for r in rows.values())
    months = {}
    for r in rows.values():
        d, m, y = r["OrderDate"].split("/")
        months[f"{y}-{m}"] = months.get(f"{y}-{m}", 0) + 1
    return {"sales_amount": f"{amount:.2f}", "orders": len({k[0] for k in rows}), "order_lines": len(rows),
            "files": len(list(folder.glob("*.csv"))), "months": len(months)}


def expected(root: Path = ROOT) -> dict:
    return {stage: {"folder": folder, **stage_values(root / folder)} for stage, folder in STAGES.items()}


if __name__ == "__main__":
    print(json.dumps(expected(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT), indent=2))
