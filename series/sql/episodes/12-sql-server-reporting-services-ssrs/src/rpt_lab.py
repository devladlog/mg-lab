"""Reporting lab runner for episode 12: the data layer of the paginated report SalesByProduct.rdl on ContosoBikesRpt.

* ``sqlserver`` - the demo. Resets and creates ContosoBikesRpt (episode 5's tables + the Rpt procedures), creates the
  read-only login rs_reader (password from RS_READER_PASSWORD), then runs the report's datasets exactly as the report
  server would (r03 default parameters, r04 one region, r05 the drop-down list), compares each result with expected/
  and checks that the columns returned are the fields the .rdl declares, in the same order. r06 checks the account's rights.
* ``duckdb``    - the local check (no server): the SELECT of each procedure (between "-- query-begin" and "-- query-end")
  runs on DuckDB with the report's default parameters, and its columns are compared with the .rdl's fields.

    python src/rpt_lab.py                                       # duckdb
    python src/rpt_lab.py --engine sqlserver --setup            # needs SQL_CONNECTION_STRING and RS_READER_PASSWORD
    python src/rpt_lab.py --engine sqlserver --reset-only       # tear-down: database and login
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from labdb import (DuckDBEngine, SqlServerEngine, diff, format_table, read_csv, split_batches,  # noqa: E402
                   to_table)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
RDL = HERE / "report" / "SalesByProduct.rdl"
DB = "ContosoBikesRpt"
RDL_NS = {"r": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"}
DEFAULTS = {"@From": "2025-03-01", "@To": "2025-04-30", "@Region": "ALL"}


@dataclass
class Step:
    key: str                      # src/sql/<key>.sql and expected/<key>.csv
    title: str
    dataset: str | None = None    # the .rdl dataset whose fields the result's columns must equal
    params: dict = field(default_factory=lambda: dict(DEFAULTS))   # local check: values of the query parameters


STEPS = [
    Step("r03-sales-by-product", "dataset SalesByProduct, default parameters", "SalesByProduct"),
    Step("r04-sales-north", "dataset SalesByProduct, Region = North", "SalesByProduct", {**DEFAULTS, "@Region": "North"}),
    Step("r05-regions", "dataset Regions (the drop-down)", "Regions"),
    Step("r06-permissions-check", "what rs_reader may do"),
]


def sql_text(name: str) -> str:
    return (SQL_DIR / (name if name.endswith(".sql") else f"{name}.sql")).read_text(encoding="utf-8")


def rdl_model() -> dict:
    """Datasets (fields, command, parameters) and report parameters, read from the .rdl."""
    from lxml import etree
    root = etree.parse(str(RDL)).getroot()
    ds = {}
    for d in root.iterfind(".//r:DataSets/r:DataSet", RDL_NS):
        ds[d.get("Name")] = {
            "fields": [f.get("Name") for f in d.iterfind("r:Fields/r:Field", RDL_NS)],
            "command": d.findtext("r:Query/r:CommandText", namespaces=RDL_NS),
            "command_type": d.findtext("r:Query/r:CommandType", namespaces=RDL_NS),
            "query_parameters": [q.get("Name") for q in d.iterfind("r:Query/r:QueryParameters/r:QueryParameter", RDL_NS)],
        }
    params = {p.get("Name"): p.findtext("r:DefaultValue/r:Values/r:Value", namespaces=RDL_NS)
              for p in root.iterfind(".//r:ReportParameters/r:ReportParameter", RDL_NS)}
    return {"datasets": ds, "parameters": params}


def proc_query(proc: str) -> str:
    """The portable SELECT between -- query-begin and -- query-end of one procedure in r01-report-objects.sql."""
    text = sql_text("r01-report-objects")
    m = re.search(rf"CREATE OR ALTER PROCEDURE {re.escape(proc)}\b(.*?)^GO", text, re.DOTALL | re.MULTILINE)
    return re.search(r"^\s*-- query-begin\s*$(.*?)^\s*-- query-end\s*$", m.group(1), re.DOTALL | re.MULTILINE).group(1).strip()


def local_query(eng: DuckDBEngine, proc: str, params: dict) -> tuple[list[str], list[tuple]]:
    sql = proc_query(proc)
    for name, value in params.items():
        sql = sql.replace(name, f"'{value}'")
    return eng.query(sql)


def local_engine() -> DuckDBEngine:
    eng = DuckDBEngine(schemas=("Sales",))
    eng.run_file(SQL_DIR / "01-schema-and-data.sql")
    return eng


PROC_OF = {"SalesByProduct": "Rpt.usp_SalesByProduct", "Regions": "Rpt.usp_Regions"}


def run_local() -> int:
    model = rdl_model()
    eng = local_engine()
    problems: list[str] = []
    try:
        for step in STEPS:
            if step.dataset is None:
                continue
            proc = PROC_OF[step.dataset]
            columns, rows = local_query(eng, proc, step.params if step.dataset == "SalesByProduct" else {})
            table = to_table(columns, rows)
            print(f"\n{step.key}: {step.title}"); print(format_table(table))
            problems += [f"{step.key}: {p}" for p in diff(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)]
            fields = model["datasets"][step.dataset]["fields"]
            if columns != fields:
                problems.append(f"{step.key}: columns {columns} != fields of dataset {step.dataset} in the .rdl {fields}")
        empty, _ = None, None
        columns, rows = local_query(eng, PROC_OF["SalesByProduct"], {**DEFAULTS, "@From": "2030-01-01", "@To": "2030-01-31"})
        print(f"\nan empty date range returns {len(rows)} rows and the same columns: {columns}")
        problems += [] if (not rows and columns == model["datasets"]["SalesByProduct"]["fields"]) else ["empty range"]
    finally:
        eng.close()
    print("\n" + ("local checks: the report's datasets match expected/ and the .rdl fields on duckdb" if not problems
                  else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def use(engine: SqlServerEngine, db: str) -> None:
    res = engine.run_script(f"USE {db};")
    if res.errors:
        raise RuntimeError(res.errors[0])


def reader_script(password: str) -> str:
    """r02-reader-login.sql with the password from the environment (never stored in the file)."""
    text = sql_text("r02-reader-login")
    text, n = re.subn(r"DECLARE @pwd nvarchar\(128\) = N'[^']*';", lambda m: "DECLARE @pwd nvarchar(128) = N'" + password.replace("'", "''") + "';", text)
    assert n == 1
    return text


def run_sqlserver(engine: SqlServerEngine, setup: bool, password: str | None) -> int:
    model = rdl_model()
    if setup:
        for f in ("r00-reset.sql", "00-create-database.sql"):
            engine.run_file(SQL_DIR / f)
        use(engine, DB)
        engine.run_file(SQL_DIR / "01-schema-and-data.sql")
        engine.run_file(SQL_DIR / "r01-report-objects.sql")
        print(f"setup: {DB} created with episode 5's tables and the Rpt procedures")
        if password:
            res = engine.run_script(reader_script(password))
            if res.errors:
                raise RuntimeError(res.errors[0])
            print("setup: login rs_reader created with EXECUTE on schema Rpt")
    failures = 0
    for step in STEPS:
        res = engine.run_script(sql_text(step.key))
        print(f"\n{step.key}: {step.title}")
        problems = [f"unexpected error: {res.errors[0][:200]}"] if res.errors else []
        if res.columns is None:
            problems.append("no result set")
        else:
            table = to_table(res.columns, res.rows)
            print(format_table(table))
            problems += diff(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)
            if step.dataset and res.columns != model["datasets"][step.dataset]["fields"]:
                problems.append(f"columns {res.columns} != fields of dataset {step.dataset}: {model['datasets'][step.dataset]['fields']}")
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(STEPS) - failures}/{len(STEPS)} steps behaved as expected on sqlserver")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: reset and recreate the database and login first")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: drop the database and the login, then stop")
    a = ap.parse_args(argv)
    if a.engine == "duckdb":
        return run_local()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")
    eng = SqlServerEngine(conn_str)
    try:
        if a.reset_only:
            eng.run_file(SQL_DIR / "r00-reset.sql")
            print("reset: database and login dropped")
            return 0
        password = os.environ.get("RS_READER_PASSWORD")
        if a.setup and not password:
            ap.error("set RS_READER_PASSWORD (the password of the new login rs_reader) for --setup")
        return run_sqlserver(eng, a.setup, password)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
