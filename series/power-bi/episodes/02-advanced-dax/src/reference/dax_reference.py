#!/usr/bin/env python3
"""Reference implementation of the episode's DAX measures, in plain Python, over the same star CSVs.

Why: DAX only runs inside the Analysis Services engine (Power BI Desktop on Windows, or the service).
This module computes what each measure *should* return for the five queries in
../ContosoSales.SemanticModel/DAXQueries, so we know the expected numbers before Desktop opens
and the recording can compare them on screen. It is not a DAX engine: each measure is written by hand,
following the documented semantics of the functions it uses (DIVIDE, SAMEPERIODLASTYEAR, DATESYTD,
DATESBETWEEN + EOMONTH, RANKX ties = Skip, BLANK arithmetic, SUMMARIZECOLUMNS dropping all-blank rows).

Usage:
    python dax_reference.py            # writes expected/*.csv and prints them
"""
import calendar
import csv
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAR = HERE.parent / "data" / "star"
BLANK = None
UNKNOWN_CUSTOMER = -1


# ---------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------
def _read(star, name):
    with open(Path(star) / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class Line:
    order_date: date
    ship_date: date
    customer: int
    product: int
    amount: Decimal


class Model:
    def __init__(self, star=STAR):
        self.products = {int(r["ProductKey"]): r for r in _read(star, "dim_product")}
        self.customers = [int(r["CustomerKey"]) for r in _read(star, "dim_customer")]
        self.dates = [date.fromisoformat(r["Date"]) for r in _read(star, "dim_date")]
        self.date_set = set(self.dates)
        self.lines = [Line(date.fromisoformat(r["OrderDate"]), date.fromisoformat(r["ShipDate"]),
                           int(r["CustomerKey"]), int(r["ProductKey"]),
                           Decimal(r["UnitPrice"]) * int(r["Quantity"]))
                      for r in _read(star, "fact_sales")]


@dataclass(frozen=True)
class Ctx:
    """A filter context: dates (None = no filter), Product column filters, one customer (or None)."""
    dates: frozenset | None = None
    product: tuple = ()          # (("Category", "Bikes"), ("Product", "Road 100"))
    customer: int | None = None

    def with_dates(self, dates):
        return replace(self, dates=frozenset(dates))

    def with_product(self, **cols):
        return replace(self, product=tuple(sorted(cols.items())))


# ---------------------------------------------------------------------------------------------
# DAX building blocks
# ---------------------------------------------------------------------------------------------
def divide(numerator, denominator):
    """DIVIDE: BLANK when the denominator is zero or BLANK (no alternate result given)."""
    if denominator is BLANK or denominator == 0:
        return BLANK
    return (numerator or Decimal(0)) / denominator if numerator is not BLANK else BLANK


def minus(a, b):
    """BLANK - BLANK = BLANK; otherwise BLANK behaves like 0 in addition/subtraction."""
    if a is BLANK and b is BLANK:
        return BLANK
    return (a or Decimal(0)) - (b or Decimal(0))


def eomonth(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, calendar.monthrange(y, m)[1])


def same_period_last_year(m: Model, dates):
    """SAMEPERIODLASTYEAR = DATEADD(dates, -1, YEAR), with the documented month-end extension:
    when the selection includes the last two days of a month, the result runs to the end of that month."""
    out = set()
    for d in dates:
        y = d.year - 1
        out.add(date(y, d.month, min(d.day, calendar.monthrange(y, d.month)[1])))
    for (y, mo) in {(d.year, d.month) for d in dates}:
        last = calendar.monthrange(y, mo)[1]
        if date(y, mo, last) in dates and date(y, mo, last - 1) in dates:
            py_last = calendar.monthrange(y - 1, mo)[1]
            out.update(date(y - 1, mo, day) for day in range(min(last - 1, py_last), py_last + 1))
    return {d for d in out if d in m.date_set}          # only dates that exist in the Date table


def dates_ytd(m: Model, dates):
    last = max(dates)
    return {d for d in m.dates if date(last.year, 1, 1) <= d <= last}


def dates_between(m: Model, first, last):
    return {d for d in m.dates if first <= d <= last}


# ---------------------------------------------------------------------------------------------
# measures
# ---------------------------------------------------------------------------------------------
def _sum(m: Model, ctx: Ctx, role="order"):
    total, found = Decimal(0), False
    pf = dict(ctx.product)
    for ln in m.lines:
        d = ln.order_date if role == "order" else ln.ship_date
        if ctx.dates is not None and d not in ctx.dates:
            continue
        if ctx.customer is not None and ln.customer != ctx.customer:
            continue
        if pf and any(m.products[ln.product][col] != val for col, val in pf.items()):
            continue
        total += ln.amount
        found = True
    return total if found else BLANK


def sales_amount(m, ctx):
    return _sum(m, ctx)


def sales_py(m, ctx):
    dates = ctx.dates if ctx.dates is not None else m.date_set
    return sales_amount(m, ctx.with_dates(same_period_last_year(m, dates)))


def sales_yoy(m, ctx):
    current, prior = sales_amount(m, ctx), sales_py(m, ctx)
    return divide(minus(current, prior), prior) if current is not BLANK else BLANK


def sales_yoy_naive(m, ctx):
    current, prior = sales_amount(m, ctx), sales_py(m, ctx)
    return divide(minus(current, prior), prior)


def sales_ytd(m, ctx):
    dates = ctx.dates if ctx.dates is not None else m.date_set
    return sales_amount(m, ctx.with_dates(dates_ytd(m, dates)))


def sales_last_3_months(m, ctx):
    dates = ctx.dates if ctx.dates is not None else m.date_set
    last = max(dates)
    first = eomonth(last, -3) + timedelta(days=1)
    return sales_amount(m, ctx.with_dates(dates_between(m, first, last)))


def sales_by_ship_date(m, ctx):
    return _sum(m, ctx, role="ship")


def product_rank(m, ctx):
    """RANKX(ALL('Product'[Product]), [Sales Amount]): descending, ties = Skip, BLANK counts as 0.
    Other Product filters (Category) stay in place, so products outside the category evaluate to BLANK."""
    current = sales_amount(m, ctx)
    if current is BLANK:
        return BLANK
    others = dict(ctx.product)
    values = []
    for name in sorted({p["Product"] for p in m.products.values()}):
        v = sales_amount(m, ctx.with_product(**{**others, "Product": name}))
        values.append(v or Decimal(0))
    return 1 + sum(1 for v in values if v > current)


def pct_of_category(m, ctx):
    keep = {k: v for k, v in ctx.product if k == "Category"}
    return divide(sales_amount(m, ctx), sales_amount(m, ctx.with_product(**keep)))


def customers_over_1k(m, ctx):
    n = 0
    for c in m.customers:
        if c == UNKNOWN_CUSTOMER:
            continue
        v = sales_amount(m, replace(ctx, customer=c))       # context transition: one customer at a time
        if v is not BLANK and v > 1000:
            n += 1
    return n or BLANK                                        # COUNTROWS of an empty table is BLANK


def customers_over_1k_no_transition(m, ctx):
    """SUMX(Sales, ...) inside FILTER's row context ignores the current customer: same total for everyone."""
    total = sales_amount(m, ctx)
    if total is BLANK or not total > 1000:
        return BLANK
    return sum(1 for c in m.customers if c != UNKNOWN_CUSTOMER) or BLANK


# ---------------------------------------------------------------------------------------------
# the five DAX queries
# ---------------------------------------------------------------------------------------------
def summarize(rows, measures):
    """SUMMARIZECOLUMNS keeps a row only if at least one expression is not BLANK."""
    return [r for r in rows if any(r[k] is not BLANK for k in measures)]


def months_of(m, year):
    return [(f"{year}-{mo:02d}", {d for d in m.dates if d.year == year and d.month == mo}) for mo in range(1, 13)]


def years_of(m):
    return [(y, {d for d in m.dates if d.year == y}) for y in sorted({d.year for d in m.dates})]


def q_time_intelligence(m):
    names = ["Sales", "Sales PY", "YoY %", "Sales YTD", "Last 3 Months"]
    rows = []
    for ym, dates in months_of(m, 2025):
        c = Ctx().with_dates(dates)
        rows.append({"Year Month": ym, "Sales": sales_amount(m, c), "Sales PY": sales_py(m, c),
                     "YoY %": sales_yoy(m, c), "Sales YTD": sales_ytd(m, c),
                     "Last 3 Months": sales_last_3_months(m, c)})
    return ["Year Month"] + names, summarize(rows, names)


def q_yoy_gotcha(m):
    names = ["Sales", "Sales PY", "YoY % naive", "YoY %"]
    rows = []
    for y, dates in years_of(m):
        c = Ctx().with_dates(dates)
        rows.append({"Year": y, "Sales": sales_amount(m, c), "Sales PY": sales_py(m, c),
                     "YoY % naive": sales_yoy_naive(m, c), "YoY %": sales_yoy(m, c)})
    return ["Year"] + names, summarize(rows, names)


def q_context_transition(m):
    names = ["Customers Over 1K", "Without transition"]
    rows = []
    for y, dates in years_of(m):
        c = Ctx().with_dates(dates)
        rows.append({"Year": y, "Customers Over 1K": customers_over_1k(m, c),
                     "Without transition": customers_over_1k_no_transition(m, c)})
    return ["Year"] + names, summarize(rows, names)


def q_ranking(m):
    names = ["Sales", "Rank", "% of Category"]
    dates = {d for d in m.dates if d.year == 2025}
    rows = []
    # SUMMARIZECOLUMNS on two columns of the same table: only existing combinations (auto-exist)
    for cat, prod in sorted({(p["Category"], p["Product"]) for p in m.products.values()}):
        c = Ctx().with_dates(dates).with_product(Category=cat, Product=prod)
        rows.append({"Category": cat, "Product": prod, "Sales": sales_amount(m, c),
                     "Rank": product_rank(m, c), "% of Category": pct_of_category(m, c)})
    rows = summarize(rows, names)
    rows.sort(key=lambda r: (r["Category"], r["Rank"] if r["Rank"] is not BLANK else 10**9))
    return ["Category", "Product"] + names, rows


def q_ship_date(m):
    names = ["By order date", "By ship date"]
    rows = []
    for y, dates in years_of(m):
        c = Ctx().with_dates(dates)
        rows.append({"Year": y, "By order date": sales_amount(m, c), "By ship date": sales_by_ship_date(m, c)})
    return ["Year"] + names, summarize(rows, names)


QUERIES = {
    "01 Time intelligence": q_time_intelligence,
    "02 YoY gotcha": q_yoy_gotcha,
    "03 Context transition": q_context_transition,
    "04 Ranking and share": q_ranking,
    "05 Ship date": q_ship_date,
}
RATIO_COLUMNS = {"YoY %", "YoY % naive", "% of Category"}


def fmt(col, v):
    if v is BLANK:
        return ""
    if isinstance(v, Decimal):
        q = Decimal("0.0001") if col in RATIO_COLUMNS else Decimal("0.01")
        return str(v.quantize(q, rounding=ROUND_HALF_UP))
    return str(v)


def run_all(m=None):
    m = m or Model()
    out = {}
    for name, fn in QUERIES.items():
        header, rows = fn(m)
        out[name] = [header] + [[fmt(h, r[h]) for h in header] for r in rows]
    return out


def write_expected(results, folder=HERE / "expected"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, table in results.items():
        with (folder / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows(table)


def main():
    results = run_all()
    write_expected(results)
    for name, table in results.items():
        print(f"\n== {name}")
        widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
        for row in table:
            print("  ".join(cell.rjust(w) for cell, w in zip(row, widths)))


if __name__ == "__main__":
    main()
