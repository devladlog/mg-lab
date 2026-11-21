"""Validated answers for the Contoso Bikes golden questions, computed straight from the star-schema CSV files.

Learn (Optimize your semantic model for Copilot): for each question, define the expected measure, grouping, date
basis, filters and a validated result, then compare what Copilot returns. This module produces those validated
results independently of Power BI, with Decimal arithmetic, so a wrong Copilot answer can be called wrong.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def default_star_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "power-bi" / "episodes" / "01-data-modeling-star-schema" / "src" / "data" / "star"
        if cand.is_dir():
            return cand
    return None


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _money(x: Decimal) -> str:
    return f"{x.quantize(CENT, ROUND_HALF_UP):,.2f}"


def compute(star_dir: str | Path, year: int = 2025, month: int = 6) -> list[dict]:
    d = Path(star_dir)
    products = {r["ProductKey"]: r for r in _rows(d / "dim_product.csv")}
    stores = {r["StoreKey"]: r for r in _rows(d / "dim_store.csv")}
    customers = {r["CustomerKey"]: r for r in _rows(d / "dim_customer.csv")}
    sales_by_year = Decimal(0)
    margin_by_cat: dict[str, Decimal] = defaultdict(Decimal)
    sales_by_store: dict[str, Decimal] = defaultdict(Decimal)
    sales_by_cust_country: dict[str, Decimal] = defaultdict(Decimal)
    sales_by_store_country: dict[str, Decimal] = defaultdict(Decimal)
    ordered_m, shipped_m = set(), set()
    ym = f"{year}-{month:02d}"
    for r in _rows(d / "fact_sales.csv"):
        qty = Decimal(r["Quantity"])
        price, cost = Decimal(r["UnitPrice"]), Decimal(r["UnitCost"])
        amount = qty * price
        if r["OrderDate"].startswith(str(year)):
            sales_by_year += amount
            margin_by_cat[products[r["ProductKey"]]["Category"]] += amount - qty * cost
            sales_by_store[stores[r["StoreKey"]]["Store"]] += amount
            sales_by_cust_country[customers[r["CustomerKey"]]["Country"]] += amount
            sales_by_store_country[stores[r["StoreKey"]]["Country"]] += amount
        if r["OrderDate"].startswith(ym):
            ordered_m.add(r["OrderNumber"])
        if r["ShipDate"].startswith(ym):
            shipped_m.add(r["OrderNumber"])
    best_cat = max(margin_by_cat.items(), key=lambda kv: kv[1])
    top3 = sorted(sales_by_store.items(), key=lambda kv: (-kv[1], kv[0]))[:3]

    def fmt(dct):
        return "; ".join(f"{k} {_money(v)}" for k, v in sorted(dct.items(), key=lambda kv: (-kv[1], kv[0])))

    return [
        {"id": "G1", "question": f"What were total sales in {year}?",
         "measure": "[Sales Amount]", "grouping": "none", "date_basis": "Order Date (active relationship)",
         "expected": _money(sales_by_year), "raw": sales_by_year},
        {"id": "G2", "question": f"Which product category made the most margin in {year}?",
         "measure": "[Margin]", "grouping": "Product[Category]", "date_basis": "Order Date",
         "expected": f"{best_cat[0]} {_money(best_cat[1])}", "raw": best_cat[1]},
        {"id": "G3", "question": f"Top three stores by sales in {year}",
         "measure": "[Sales Amount]", "grouping": "Store[Store]", "date_basis": "Order Date",
         "expected": "; ".join(f"{k} {_money(v)}" for k, v in top3), "raw": [v for _, v in top3]},
        {"id": "G4", "question": f"How many orders were shipped in {MONTHS[month - 1]} {year}?",
         "measure": "[Orders]", "grouping": "none",
         "date_basis": "Ship Date (inactive relationship: needs USERELATIONSHIP)",
         "expected": f"{len(shipped_m)} shipped (the {len(ordered_m)} is the order-date answer)", "raw": len(shipped_m)},
        {"id": "G5", "question": f"Show sales by country for {year}",
         "measure": "[Sales Amount]", "grouping": "Customer[Country] or Store[Country]: ambiguous on purpose",
         "date_basis": "Order Date",
         "expected": f"by customer country: {fmt(sales_by_cust_country)} | by store country: {fmt(sales_by_store_country)}",
         "raw": None},
    ]
