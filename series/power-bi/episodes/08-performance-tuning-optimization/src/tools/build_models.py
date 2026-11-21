#!/usr/bin/env python3
"""Generate the two semantic models of the episode from one description, so the DIFFERENCE between them is the lesson.

  ContosoPerf.Before.SemanticModel   the model that outgrew the report: everything the lint rules PF001-PF009 look for
  ContosoPerf.After.SemanticModel    the same model, tuned. Same tables, same measure names, same totals.

Everything that differs is marked  # BEFORE / AFTER  below. Both are TMDL folders Power BI Desktop opens as a Power BI
Project (the .pbip files sit beside them), and both read the CSV files gen_sales.py writes into the DataFolder parameter.

    python build_models.py           # rewrite both folders
    python build_models.py --check   # exit 1 if the committed files differ from this description
"""
import argparse
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
TARGETS = {"before": SRC / "ContosoPerf.Before.SemanticModel", "after": SRC / "ContosoPerf.After.SemanticModel"}


def q(name):
    return f"'{name}'" if any(c in name for c in " -%") else name


def m_block(lines):
    """A partition M expression, indented the way TMDL wants it (4 tabs, M's own 4 spaces inside let)."""
    return "\n".join("\t\t\t\t" + l for l in lines)


def csv_partition(table, csv, types, extra_steps=None, last="Typed", select=None):
    steps = [f'Source = Csv.Document(File.Contents(DataFolder & "\\{csv}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
             "Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),"]
    prev = "Promoted"
    if select:
        names = ", ".join('"%s"' % n for n in select)
        steps.append(f"Columns = Table.SelectColumns(Promoted, {{{names}}}),")
        prev = "Columns"
    cols = ", ".join('{"%s", %s}' % (n, t) for n, t in types)
    steps.append(f'Typed = Table.TransformColumnTypes({prev}, {{{cols}}}, "en-US")' + ("," if extra_steps else ""))
    if extra_steps:
        steps += extra_steps
    body = ["let"] + ["    " + s for s in steps] + ["in", f"    {last}"]
    return f"\tpartition {table} = m\n\t\tmode: import\n\t\tsource =\n{m_block(body)}\n"


def col(name, dtype, source=None, hidden=False, key=False, fmt=None, summarize="none", sort=None, expr=None):
    out = [f"\tcolumn {q(name)}" + (f" = {expr}" if expr else ""), f"\t\tdataType: {dtype}"]
    if hidden:
        out.append("\t\tisHidden")
    if key:
        out.append("\t\tisKey")
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    out.append(f"\t\tsummarizeBy: {summarize}")
    if source:
        out.append(f"\t\tsourceColumn: {source}")
    if sort:
        out.append(f"\t\tsortByColumn: {q(sort)}")
    return "\n".join(out) + "\n"


def table(name, doc, parts, extra=""):
    return f"/// {doc}\ntable {q(name)}{extra}\n\n" + "\n".join(parts)


def measure(name, expr, fmt=None, folder="Base", doc=None):
    head = (f"\t/// {doc}\n" if doc else "") + f"\tmeasure {q(name)} ="
    lines = expr.strip("\n").split("\n")
    if len(lines) == 1:
        body = f" {lines[0]}\n"
    else:
        body = "\n" + "\n".join("\t\t\t" + l for l in lines) + "\n"
    s = head + body.rstrip("\n") if len(lines) > 1 else head + body.rstrip("\n")
    s += "\n"
    if fmt:
        s += f"\t\tformatString: {fmt}\n"
    s += f"\t\tdisplayFolder: {folder}\n"
    return s


def dimension_tables():
    t = {}
    t["Store"] = table("Store", "Store dimension (physical stores and the online shop).", [
        col("StoreKey", "int64", "StoreKey", True, True, "0"), col("Store", "string", "Store"),
        col("Country", "string", "Country"), col("Channel", "string", "Channel"),
        csv_partition("Store", "store.csv", [("StoreKey", "Int64.Type")])])
    t["Product"] = table("Product", "Product dimension. Category and subcategory are flattened into this table.", [
        col("ProductKey", "int64", "ProductKey", True, True, "0"), col("Product", "string", "Product"),
        col("Category", "string", "Category"), col("Subcategory", "string", "Subcategory"),
        csv_partition("Product", "product.csv", [("ProductKey", "Int64.Type"), ("ListPrice", "Currency.Type")])])
    t["Customer"] = table("Customer", "Customer dimension: 5,000 fictional customers.", [
        col("CustomerKey", "int64", "CustomerKey", True, True, "0"), col("Customer Code", "string", "CustomerCode"),
        col("Customer", "string", "Customer"), col("City", "string", "City"), col("Country", "string", "Country"),
        csv_partition("Customer", "customer.csv", [("CustomerKey", "Int64.Type")])])
    t["Date"] = table("Date", "Date dimension: one row per day, marked as the date table. Filters Sales by order date.", [
        col("Date", "dateTime", "Date", key=True, fmt="yyyy-mm-dd"), col("Year", "int64", "Year", fmt="0"),
        col("Quarter", "string", "Quarter"),
        col("Month Number", "int64", "MonthNumber", True, fmt="0"),
        col("Month", "string", "Month", sort="Month Number"),
        col("Year Month Number", "int64", "YearMonthNumber", True, fmt="0"),
        col("Year Month", "string", "YearMonth", sort="Year Month Number"),
        csv_partition("Date", "date.csv", [("Date", "type date"), ("Year", "Int64.Type"), ("MonthNumber", "Int64.Type"),
                                           ("YearMonthNumber", "Int64.Type")])], "\n\tdataCategory: Time")
    return t


# the measures both models share, written once; the BEFORE / AFTER variants follow
def measures(side):
    before = side == "before"
    m = []
    m.append(measure("Sales Amount", "SUM(Sales[Line Amount])", "#,0.00",
                     doc="Sum of the line amount column (a DAX calculated column in the before model, a Power Query column in the after model)."))
    m.append(measure("Total Cost", "SUMX(Sales, Sales[Quantity] * Sales[Unit Cost])", "#,0.00"))
    m.append(measure("Margin", "[Sales Amount] - [Total Cost]", "#,0.00"))
    if before:  # BEFORE: IFERROR hides every error, / on a measure denominator
        m.append(measure("Margin %", "IFERROR([Margin] / [Sales Amount], 0)", "0.0%"))
    else:       # AFTER: DIVIDE returns BLANK when the denominator is zero or blank
        m.append(measure("Margin %", "DIVIDE([Margin], [Sales Amount])", "0.0%"))
    m.append(measure("Units", "SUM(Sales[Quantity])", "#,0"))
    m.append(measure("Orders", "DISTINCTCOUNT(Sales[Order Number])", "#,0"))
    m.append(measure("Sales PY", "CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date]))", "#,0.00", "Time intelligence"))
    if before:  # BEFORE: the same CALCULATE twice
        m.append(measure("Sales YoY %",
                         "DIVIDE(\n    [Sales Amount] - CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date])),\n"
                         "    CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date]))\n)", "0.0%", "Time intelligence"))
    else:       # AFTER: one variable, used twice
        m.append(measure("Sales YoY %",
                         "VAR PriorSales = CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date]))\nRETURN\n"
                         "    DIVIDE([Sales Amount] - PriorSales, PriorSales)", "0.0%", "Time intelligence"))
    if before:  # BEFORE: FILTER over the whole Store table as a filter argument
        m.append(measure("Online Sales", "CALCULATE([Sales Amount], FILTER('Store', 'Store'[Channel] = \"Online\"))",
                         "#,0.00", "Channels"))
    else:       # AFTER: a Boolean filter argument. Not identical: KEEPFILTERS keeps a Store slicer, FILTER dropped it.
        m.append(measure("Online Sales", "CALCULATE([Sales Amount], KEEPFILTERS('Store'[Channel] = \"Online\"))",
                         "#,0.00", "Channels"))
    return m


def sales_table(side):
    before = side == "before"
    parts = ["\n".join(measures(side))]
    cols = []
    cols.append(col("Order Number", "string" if before else "int64", "OrderNumber", fmt=None if before else "0"))
    if before:
        cols.append(col("Order Timestamp", "dateTime", "OrderTimestamp", True, fmt="yyyy-mm-dd hh:mm:ss"))
    cols += [col("Order Date", "dateTime", "OrderDate", True, fmt="yyyy-mm-dd"),
             col("Ship Date", "dateTime", "ShipDate", True, fmt="yyyy-mm-dd"),
             col("CustomerKey", "int64", "CustomerKey", True, fmt="0"), col("ProductKey", "int64", "ProductKey", True, fmt="0"),
             col("StoreKey", "int64", "StoreKey", True, fmt="0"), col("Quantity", "int64", "Quantity", True, fmt="#,0"),
             col("Unit Cost", "decimal", "UnitCost", True, fmt="#,0.00")]
    if before:
        cols.insert(len(cols) - 1, col("Unit Price", "decimal", "UnitPrice", True, fmt="#,0.00"))  # BEFORE: columns nothing uses, and a calculated column
        cols += [col("Line Ref", "string", "LineRef", True), col("Note", "string", "Note", True),
                 col("Line Amount", "decimal", None, True, fmt="#,0.00", expr="Sales[Quantity] * Sales[Unit Price]")]
        types = [("OrderNumber", "type text"), ("OrderTimestamp", "type datetime"), ("ShipDate", "type date"),
                 ("CustomerKey", "Int64.Type"), ("ProductKey", "Int64.Type"), ("StoreKey", "Int64.Type"),
                 ("Quantity", "Int64.Type"), ("UnitPrice", "Currency.Type"), ("UnitCost", "Currency.Type"),
                 ("LineRef", "type text"), ("Note", "type text")]
        part = csv_partition("Sales", "sales_detail.csv", types, [
            'WithOrderDate = Table.AddColumn(Typed, "OrderDate", each DateTime.Date([OrderTimestamp]), type date)'],
            "WithOrderDate")
    else:       # AFTER: only the columns the reports use, a date instead of a timestamp, a number instead of 'SO-...'
        cols += [col("Line Amount", "decimal", "LineAmount", True, fmt="#,0.00")]
        types = [("OrderTimestamp", "type datetime"), ("ShipDate", "type date"), ("CustomerKey", "Int64.Type"),
                 ("ProductKey", "Int64.Type"), ("StoreKey", "Int64.Type"), ("Quantity", "Int64.Type"),
                 ("UnitPrice", "Currency.Type"), ("UnitCost", "Currency.Type")]
        steps = ['OrderDate = Table.AddColumn(Typed, "OrderDate", each DateTime.Date([OrderTimestamp]), type date),',
                 'OrderNumber = Table.TransformColumns(OrderDate, {{"OrderNumber", each Number.FromText(Text.AfterDelimiter(_, "-")), Int64.Type}}),',
                 'LineAmount = Table.AddColumn(OrderNumber, "LineAmount", each [Quantity] * [UnitPrice], Currency.Type),',
                 'Result = Table.RemoveColumns(LineAmount, {"OrderTimestamp", "UnitPrice"})']
        part = csv_partition("Sales", "sales_detail.csv", types, steps, "Result", select=[
            "OrderNumber", "OrderTimestamp", "ShipDate", "CustomerKey", "ProductKey", "StoreKey", "Quantity",
            "UnitPrice", "UnitCost"])
    parts += ["\n".join(cols), part]
    return table("Sales", "Fact table, one row per order line.", parts)


def relationships(side):
    before = side == "before"
    r = ["relationship 'Sales Order Date to Date'\n\tfromColumn: Sales.'Order Date'\n\ttoColumn: Date.Date\n",
         "relationship 'Sales Ship Date to Date'\n\tisActive: false\n\tfromColumn: Sales.'Ship Date'\n\ttoColumn: Date.Date\n",
         "relationship 'Sales to Customer'\n\tfromColumn: Sales.CustomerKey\n\ttoColumn: Customer.CustomerKey\n",
         # BEFORE: both directions on Product (someone wanted slicers 'with data'); AFTER: single direction
         "relationship 'Sales to Product'\n" + ("\tcrossFilteringBehavior: bothDirections\n" if before else "")
         + "\tfromColumn: Sales.ProductKey\n\ttoColumn: Product.ProductKey\n",
         "relationship 'Sales to Store'\n\tfromColumn: Sales.StoreKey\n\ttoColumn: Store.StoreKey\n"]
    return "\n".join(r)


AUTO_DATE = """/// The hidden table Power BI Desktop adds for every date column while Auto date/time is on (re-created here by hand:
/// Desktop writes it itself). It is a calculated table built with CALENDAR.
table LocalDateTable_OrderDate
	isHidden
	showAsVariationsOnly

	column Date
		dataType: dateTime
		isHidden
		formatString: General Date
		summarizeBy: none
		sourceColumn: [Date]

	column Year
		dataType: int64
		isHidden
		summarizeBy: none
		sourceColumn: [Year]

	partition LocalDateTable_OrderDate = calculated
		mode: import
		source = ADDCOLUMNS(CALENDAR(DATE(2023, 1, 1), DATE(2025, 12, 31)), "Year", YEAR([Date]))
"""


def render(side):
    files = {}
    dims = dimension_tables()
    tables = ["Sales", "Date", "Product", "Customer", "Store"] + (["LocalDateTable_OrderDate"] if side == "before" else [])
    files["definition.pbism"] = ('{\n  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/'
                                 'definitionProperties/1.0.0/schema.json",\n  "version": "4.0",\n  "settings": {}\n}\n')
    files["definition/database.tmdl"] = f"database ContosoPerf{side.capitalize()}\n\tcompatibilityLevel: 1600\n"
    files["definition/model.tmdl"] = ("model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
                                      "\tdiscourageImplicitMeasures\n\n" + "\n".join(f"ref table {q(t)}" for t in tables) + "\n")
    files["definition/expressions.tmdl"] = (
        "/// Folder with the CSV files gen_sales.py wrote (no trailing backslash). Change it with Transform data > Edit parameters.\n"
        'expression DataFolder = "C:\\ContosoBikesPerf" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n')
    files["definition/relationships.tmdl"] = relationships(side)
    files["definition/tables/Sales.tmdl"] = sales_table(side)
    for name, text in dims.items():
        files[f"definition/tables/{name}.tmdl"] = text
    if side == "before":
        files["definition/tables/LocalDateTable_OrderDate.tmdl"] = AUTO_DATE
    return files


def pbip(side):
    n = side.capitalize()
    import json
    return json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                       "version": "1.0", "artifacts": [{"report": {"path": f"ContosoPerf.{n}.Report"}}],
                       "settings": {"enableAutoRecovery": True}}, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = False
    for side, folder in TARGETS.items():
        wanted = render(side)
        wanted_beside = {SRC / f"ContosoPerf.{side.capitalize()}.pbip": pbip(side)}
        if a.check:
            for k, v in wanted.items():
                if not (folder / k).exists() or (folder / k).read_text(encoding="utf-8") != v:
                    print(f"{folder.name}: out of date: {k}")
                    bad = True
            for p, v in wanted_beside.items():
                if not p.exists() or p.read_text(encoding="utf-8") != v:
                    print(f"{p.name}: out of date")
                    bad = True
            have = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()} if folder.exists() else set()
            for k in sorted(have - set(wanted)):
                print(f"{folder.name}: not in the description: {k}")
                bad = True
            continue
        if folder.exists():
            shutil.rmtree(folder)
        for k, v in wanted.items():
            (folder / k).parent.mkdir(parents=True, exist_ok=True)
            (folder / k).write_text(v, encoding="utf-8", newline="\n")
        for p, v in wanted_beside.items():
            p.write_text(v, encoding="utf-8", newline="\n")
        print(f"wrote {len(wanted)} files to {folder.name}")
    if a.check:
        print("models match the description" if not bad else "models differ from the description")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
