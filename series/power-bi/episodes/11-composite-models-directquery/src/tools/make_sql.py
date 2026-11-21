#!/usr/bin/env python3
"""Star schema CSVs -> SQL for the ContosoBikesDW database, in two dialects.

  python3 make_sql.py --out ../sql                       # the T-SQL files that run on SQL Server 2022 (committed)
  python3 make_sql.py --check --out ../sql               # fails when the committed files are out of date
  python3 make_sql.py --dialect sqlite --out /tmp/sqlite # same tables, views and scale-up for SQLite (used by the tests)

Why two dialects: the container has no SQL Server (no Docker), so the tests run the SAME data, view and scale-up logic on SQLite
and prove the totals. The T-SQL files are parsed by sqlglot in the tests, and run for real on the lab SQL VM (see demo.md).
SQL column names are the CSV headers without spaces (`Month Number` -> `MonthNumber`), the TMDL `sourceColumn`s use those names.
"""
import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAR = HERE.parent / "data" / "star"
DATABASE = "ContosoBikesDW"
BATCH = 1000          # rows per INSERT ... VALUES (SQL Server allows at most 1,000)
COPIES = 499          # scale-up: 4,071 order lines x (1 + 499) = 2,035,500 rows
FACT_ROWS = 4071      # order lines in fact_sales.csv (a test checks it)

# (csv file, table, [(csv header, sql type, sqlite type)], primary key columns)
TABLES = [
    ("dim_date.csv", "DimDate", [
        ("Date", "date", "TEXT"), ("Year", "int", "INTEGER"), ("Quarter", "char(2)", "TEXT"),
        ("Month Number", "int", "INTEGER"), ("Month", "char(3)", "TEXT"), ("Year Month", "char(7)", "TEXT"),
        ("Year Month Number", "int", "INTEGER"), ("Day of Week Number", "int", "INTEGER"), ("Day of Week", "char(3)", "TEXT")], ["Date"]),
    ("dim_product.csv", "DimProduct", [
        ("ProductKey", "int", "INTEGER"), ("ProductCode", "varchar(20)", "TEXT"), ("Product", "varchar(60)", "TEXT"),
        ("Subcategory", "varchar(40)", "TEXT"), ("Category", "varchar(40)", "TEXT"), ("Color", "varchar(20)", "TEXT")], ["ProductKey"]),
    ("dim_customer.csv", "DimCustomer", [
        ("CustomerKey", "int", "INTEGER"), ("CustomerCode", "varchar(10) NULL", "TEXT"), ("Customer", "varchar(80)", "TEXT"),
        ("City", "varchar(40)", "TEXT"), ("Country", "varchar(40)", "TEXT")], ["CustomerKey"]),
    ("dim_store.csv", "DimStore", [
        ("StoreKey", "int", "INTEGER"), ("Store", "varchar(40)", "TEXT"), ("Country", "varchar(40)", "TEXT"),
        ("Channel", "varchar(20)", "TEXT")], ["StoreKey"]),
]
FACT_COLUMNS = [
    ("OrderNumber", "varchar(20)", "TEXT"), ("LineNumber", "int", "INTEGER"), ("OrderDate", "date", "TEXT"), ("ShipDate", "date", "TEXT"),
    ("CustomerKey", "int", "INTEGER"), ("ProductKey", "int", "INTEGER"), ("StoreKey", "int", "INTEGER"),
    ("Quantity", "int", "INTEGER"), ("UnitPrice", "decimal(10,2)", "NUMERIC"), ("UnitCost", "decimal(10,2)", "NUMERIC")]
FOREIGN_KEYS = [("CustomerKey", "DimCustomer"), ("ProductKey", "DimProduct"), ("StoreKey", "DimStore"), ("OrderDate", "DimDate", "Date")]


def sql_name(header: str) -> str:
    return header.replace(" ", "")


def schema(dialect: str, table: str) -> str:
    return f"dbo.{table}" if dialect == "tsql" else table


def read(csv_name: str):
    with (STAR / csv_name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def literal(value: str, sql_type: str, dialect: str) -> str:
    base = sql_type.split("(")[0].split(" ")[0]
    if value == "" and "NULL" in sql_type:
        return "NULL"
    if base in ("int", "decimal"):
        return value
    return "'" + value.replace("'", "''") + "'"


def inserts(dialect: str, table: str, columns, rows) -> list[str]:
    names = ", ".join(sql_name(c[0]) for c in columns)
    out = []
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        values = ",\n".join("    (" + ", ".join(literal(r[c[0]], c[1], dialect) for c in columns) + ")" for r in chunk)
        out.append(f"INSERT INTO {schema(dialect, table)} ({names}) VALUES\n{values};")
    return out


def column_def(dialect: str, name: str, sql_type: str, lite: str) -> str:
    if dialect != "tsql":
        return f"    {name} {lite}"
    nullable = sql_type.endswith(" NULL")
    return f"    {name} {sql_type.removesuffix(' NULL')} {'NULL' if nullable else 'NOT NULL'}"


def create_tables(dialect: str) -> list[str]:
    out = []
    for _csv, table, cols, pk in TABLES:
        lines = [column_def(dialect, sql_name(h), ty, lite) for h, ty, lite in cols]
        lines.append(f"    CONSTRAINT PK_{table} PRIMARY KEY ({', '.join(sql_name(c) for c in pk)})")
        out.append(f"CREATE TABLE {schema(dialect, table)} (\n" + ",\n".join(lines) + "\n);")
    lines = [column_def(dialect, h, ty, lite) for h, ty, lite in FACT_COLUMNS]
    if dialect == "tsql":
        lines.append("    LineAmount AS CONVERT(decimal(18,2), Quantity * UnitPrice) PERSISTED")
        lines.append("    LineCost AS CONVERT(decimal(18,2), Quantity * UnitCost) PERSISTED")
    else:
        lines.append("    LineAmount NUMERIC GENERATED ALWAYS AS (ROUND(Quantity * UnitPrice, 2)) STORED")
        lines.append("    LineCost NUMERIC GENERATED ALWAYS AS (ROUND(Quantity * UnitCost, 2)) STORED")
    lines.append("    CONSTRAINT PK_FactSales PRIMARY KEY (OrderNumber, LineNumber)")
    for fk in FOREIGN_KEYS:
        col, ref = fk[0], fk[1]
        refcol = fk[2] if len(fk) > 2 else col
        lines.append(f"    CONSTRAINT FK_FactSales_{ref} FOREIGN KEY ({col}) REFERENCES {schema(dialect, ref)} ({refcol})")
    out.append(f"CREATE TABLE {schema(dialect, 'FactSales')} (\n" + ",\n".join(lines) + "\n);")
    return out


AGG_SELECT = """SELECT f.OrderDate, f.ProductKey, f.StoreKey,
       CAST(SUM(f.Quantity) AS int) AS Units,
       CAST(SUM(f.LineAmount) AS {dec}) AS LineAmount,
       CAST(SUM(f.LineCost) AS {dec}) AS LineCost,
       {count} AS OrderLines
FROM {fact} AS f
GROUP BY f.OrderDate, f.ProductKey, f.StoreKey"""


def agg_view(dialect: str) -> str:
    if dialect == "tsql":
        sel = AGG_SELECT.format(dec="decimal(18,2)", count="COUNT_BIG(*)", fact="dbo.FactSales")
        return f"CREATE OR ALTER VIEW dbo.vwSalesAgg AS\n{sel};"
    sel = AGG_SELECT.format(dec="NUMERIC", count="COUNT(*)", fact="FactSales")
    return f"CREATE VIEW vwSalesAgg AS\n{sel};"


FACT_INSERT_COLS = "OrderNumber, LineNumber, OrderDate, ShipDate, CustomerKey, ProductKey, StoreKey, Quantity, UnitPrice, UnitCost"


def scale_up(dialect: str, copies: int = COPIES) -> str:
    if dialect == "tsql":
        return f"""SET NOCOUNT ON;
DECLARE @copies int = {copies};   -- {FACT_ROWS} x (1 + {copies}) order lines
IF EXISTS (SELECT 1 FROM dbo.FactSales WHERE OrderNumber LIKE '%-%')
    THROW 50000, 'FactSales is already scaled up (order numbers with a copy suffix exist). Run 01 and 02 again to start over.', 1;

;WITH n AS (
    SELECT TOP (@copies) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS CopyNo
    FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b
)
INSERT INTO dbo.FactSales ({FACT_INSERT_COLS})
SELECT f.OrderNumber + '-' + RIGHT('0000' + CAST(n.CopyNo AS varchar(4)), 4),
       f.LineNumber, f.OrderDate, f.ShipDate, f.CustomerKey, f.ProductKey, f.StoreKey, f.Quantity, f.UnitPrice, f.UnitCost
FROM dbo.FactSales AS f CROSS JOIN n;

SELECT COUNT_BIG(*) AS OrderLines, SUM(LineAmount) AS SalesAmount FROM dbo.FactSales;"""
    return f"""WITH RECURSIVE n(CopyNo) AS (
    SELECT 1 UNION ALL SELECT CopyNo + 1 FROM n WHERE CopyNo < {copies}
)
INSERT INTO FactSales ({FACT_INSERT_COLS})
SELECT f.OrderNumber || '-' || substr('0000' || n.CopyNo, -4),
       f.LineNumber, f.OrderDate, f.ShipDate, f.CustomerKey, f.ProductKey, f.StoreKey, f.Quantity, f.UnitPrice, f.UnitCost
FROM FactSales AS f CROSS JOIN n;"""


def build(dialect: str) -> dict[str, str]:
    files: dict[str, str] = {}
    t = dialect == "tsql"
    head = (f"-- {DATABASE}: the Contoso Bikes star schema of episode 1, as a SQL Server database (generated by tools/make_sql.py, do not edit).\n")
    if t:
        files["01-create-database.sql"] = head + f"""-- Run on the lab SQL Server (SQL Server 2022 Developer, default instance), connected to master. Fictional data only.
IF DB_ID(N'{DATABASE}') IS NOT NULL
BEGIN
    ALTER DATABASE [{DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE [{DATABASE}];
END
GO
CREATE DATABASE [{DATABASE}];
GO
ALTER DATABASE [{DATABASE}] SET RECOVERY SIMPLE;   -- the scale-up script inserts about two million rows
GO
USE [{DATABASE}];
GO
""" + "\nGO\n".join(create_tables(dialect)) + "\nGO\n"
        load = [head + f"-- Loads the five CSV files of src/data/star ({sum(len(read(c)) for c, *_ in TABLES) + len(read('fact_sales.csv'))} rows). Run after 01.\nUSE [{DATABASE}];\nGO\nSET NOCOUNT ON;"]
    else:
        files["01-create-database.sql"] = "\n".join(create_tables(dialect)) + "\n"
        load = []
    for csv_name, table, cols, _pk in TABLES:
        load += inserts(dialect, table, cols, read(csv_name))
    load += inserts(dialect, "FactSales", FACT_COLUMNS, read("fact_sales.csv"))
    files["02-load-data.sql"] = ("\nGO\n".join(load) if t else "\n".join(load)) + ("\nGO\n" if t else "\n")
    if t:
        files["03-agg-view.sql"] = head + f"-- The aggregation grain of the model's Sales Agg table: Order Date x Product x Store.\nUSE [{DATABASE}];\nGO\n{agg_view(dialect)}\nGO\n"
        files["04-scale-up.sql"] = head + f"-- Optional: copies every order line {COPIES} times (new order numbers with a -0001 .. -{COPIES:04d} suffix) so DirectQuery has something to chew on.\n-- Totals become exactly {COPIES + 1} times the original ones; the aggregation view still returns the same number of rows.\nUSE [{DATABASE}];\nGO\n{scale_up(dialect)}\nGO\n"
    else:
        files["03-agg-view.sql"] = agg_view(dialect) + "\n"
        files["04-scale-up.sql"] = scale_up(dialect) + "\n"
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dialect", choices=["tsql", "sqlite"], default="tsql")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    files = build(a.dialect)
    if a.check:
        bad = [n for n, text in files.items() if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != text]
        for n in bad:
            print(f"out of date: {out / n}")
        print("up to date" if not bad else f"{len(bad)} file(s) out of date, run tools/make_sql.py --out {out}")
        return 1 if bad else 0
    out.mkdir(parents=True, exist_ok=True)
    for n, text in files.items():
        (out / n).write_text(text, encoding="utf-8")
        print(f"wrote {out / n} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
