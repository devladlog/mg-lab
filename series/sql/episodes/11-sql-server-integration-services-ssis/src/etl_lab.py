"""SSIS lab runner for episode 11: the partner sales load (PartnerSalesLoad.dtsx) and what it leaves in ContosoBikesEtl.

* ``sqlserver`` - the demo. Resets and creates ContosoBikesEtl (episode 5's tables + the ETL objects), optionally deploys
  the project to the SSIS catalog (c00, c01), then runs the package three times from the catalog (c02) and compares
  the result of each run (c03) with expected/: the first file at the Basic logging level, the same file again at Verbose
  (nothing may be inserted twice), and the next day's file with one correction.
* ``duckdb``    - the local check (no server, no SSIS). The package itself cannot run here, so the check models its data
  flow: it reads the sample CSV with the columns the .dtsx declares, applies the Conditional Split rule taken from the
  .dtsx, lands the rows like the two OLE DB destinations do, then runs the statements of Etl.usp_MergePartnerSales
  (the text between "-- merge-begin" and "-- merge-end" of e01-etl-objects.sql) on DuckDB.

    python src/etl_lab.py                                      # duckdb: the data flow model + the merge statements
    python src/etl_lab.py --engine sqlserver --setup --deploy  # needs SQL_CONNECTION_STRING; SSIS + SSISDB on the server
    python src/etl_lab.py --engine sqlserver --reset-only      # tear-down: catalog folder, then the database
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import decimal
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from labdb import (DuckDBEngine, SqlServerEngine, diff, format_table, read_csv, split_batches,  # noqa: E402
                   to_table)

SQL_DIR = HERE / "sql"
DATA_DIR = HERE.parent / "data"
EXPECTED_DIR = HERE.parent / "expected"
DTSX = HERE / "package" / "PartnerSalesLoad.dtsx"
DB = "ContosoBikesEtl"
REMOTE_IN = "C:\\MGLab\\ssis\\in\\"
FILE1, FILE2 = "partner-sales-2025-05-21.csv", "partner-sales-2025-05-22.csv"
LOCAL_ONLY_SKIP = {"Execution status", "Rows sent by Flat File Source (data statistics)"}   # need the SSIS catalog


@dataclass
class Run:
    key: str            # expected/<key>.csv
    title: str
    file: str
    logging_level: int


RUNS = [
    Run("c03-run1-basic", "first file, Basic logging", FILE1, 1),
    Run("c03-run2-rerun-verbose", "the same file again, Verbose logging: no duplicates", FILE1, 3),
    Run("c03-run3-correction", "next day's file: two new lines and one correction", FILE2, 3),
]


def sql_text(name: str) -> str:
    return (SQL_DIR / (name if name.endswith(".sql") else f"{name}.sql")).read_text(encoding="utf-8")


# ---------------------------------------------------------------- the package, read back from the .dtsx
DTS = "{www.microsoft.com/SqlServer/Dts}"


def package_model() -> dict:
    """Columns of the flat file connection manager (name, SSIS type number) and the Conditional Split rule."""
    from lxml import etree
    root = etree.parse(str(DTSX)).getroot()
    cols = [(c.get(DTS + "ObjectName"), int(c.get(DTS + "DataType"))) for c in root.iter(DTS + "FlatFileColumn")]
    rule = None
    for p in root.iter("property"):
        if p.get("name") == "FriendlyExpression":
            rule = p.text
    return {"columns": cols, "rule": rule}


def parse_value(text: str, ssis_type: int):
    if ssis_type == 130:
        return text
    if ssis_type == 3:
        return int(text)
    if ssis_type == 133:
        return dt.date.fromisoformat(text)
    if ssis_type == 131:
        return decimal.Decimal(text)
    raise ValueError(f"unsupported SSIS type {ssis_type}")


def read_flat_file(path: Path, model: dict) -> list[dict]:
    """Flat File Source: header row, comma, text qualifier ", the columns and types of the connection manager."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    names = [n for n, _ in model["columns"]]
    if header != names:
        raise ValueError(f"{path.name}: header {header} does not match the package columns {names}")
    return [{n: parse_value(v, t) for (n, t), v in zip(model["columns"], r)} for r in body]


def evaluate_rule(rule: str, row: dict) -> bool:
    """The Conditional Split condition. Only what the package uses: comparisons joined by && and ||."""
    py = rule.replace("&&", " and ").replace("||", " or ")
    if re.search(r"[^\w\s<>=!.()+\-*/]", py):
        raise ValueError(f"expression not supported by the local model: {rule}")
    return bool(eval(py, {"__builtins__": {}}, dict(row)))   # noqa: S307 - names and numbers only, checked above


def split_rows(rows: list[dict], rule: str) -> tuple[list[dict], list[dict]]:
    valid = [r for r in rows if evaluate_rule(rule, r)]
    return valid, [r for r in rows if not evaluate_rule(rule, r)]


# ---------------------------------------------------------------- the merge statements, from the procedure
def merge_statements() -> dict[str, str]:
    """{step name: statement} of Etl.usp_MergePartnerSales between -- merge-begin and -- merge-end."""
    text = sql_text("e01-etl-objects")
    body = re.search(r"^\s*-- merge-begin\s*$(.*?)^\s*-- merge-end\s*$", text, re.DOTALL | re.MULTILINE).group(1)
    steps: dict[str, str] = {}
    for chunk in re.split(r"^\s*-- step: ", body, flags=re.MULTILINE)[1:]:
        first, _, rest = chunk.partition("\n")
        name = first.split(" ")[0]
        sql = "\n".join(ln for ln in rest.splitlines() if not ln.strip().upper().startswith("SET @")).strip()
        steps[name] = sql
    return steps


def create_table_batches() -> list[str]:
    return [b for b in split_batches(sql_text("e01-etl-objects")) if b.lstrip().upper().startswith("CREATE TABLE")]


def duckdb_identity(eng, batch: str) -> str:
    """Local check only. DuckDB has no IDENTITY(1,1) (the column gets a DEFAULT nextval() on a sequence) and no foreign
    keys across schemas (the REFERENCES clauses are dropped; SQL Server enforces them in the lab)."""
    batch = re.sub(r"\s+CONSTRAINT \w+ REFERENCES [\w.]+ \(\w+\)", "", batch)
    m = re.search(r"CREATE TABLE (\w+)\.(\w+)", batch)
    seq = f"seq_{m.group(1)}_{m.group(2)}"
    if "IDENTITY(1,1)" not in batch:
        return batch
    eng.con.execute(f"CREATE SEQUENCE {seq} START 1")
    return batch.replace("IDENTITY(1,1)", "").replace("NOT NULL CONSTRAINT PK_", f"NOT NULL DEFAULT nextval('{seq}') CONSTRAINT PK_", 1)


def local_setup() -> DuckDBEngine:
    eng = DuckDBEngine(schemas=("Sales", "Stg", "Etl"))
    eng.run_file(SQL_DIR / "01-schema-and-data.sql")
    for b in create_table_batches():
        eng.execute(duckdb_identity(eng, b))
    return eng


def insert_rows(eng, table: str, rows: list[dict]) -> None:
    for r in rows:
        cols = ", ".join(r)
        vals = ", ".join(f"'{v}'" if isinstance(v, (str, dt.date)) else str(v) for v in r.values())
        eng.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals});")


def local_run(eng, model: dict, file: str) -> dict:
    """One package run on the model: Prepare load -> data flow -> merge."""
    eng.execute("DELETE FROM Stg.PartnerSales;")                        # usp_PrepareLoad: TRUNCATE (DuckDB: DELETE)
    eng.execute(f"INSERT INTO Etl.RunLog (ExecutionId, SourceFile) VALUES (0, '{file}');")
    run_id = eng.query("SELECT MAX(RunLogId) FROM Etl.RunLog")[1][0][0]
    rows = read_flat_file(DATA_DIR / file, model)
    valid, rejected = split_rows(rows, model["rule"])
    insert_rows(eng, "Stg.PartnerSales", valid)                         # destination 1
    insert_rows(eng, "Etl.RejectedRows", rejected)                      # destination 2
    counts = {}
    for name, sql in merge_statements().items():
        cur = eng.con.execute(eng_sql(sql.replace("@RunLogId", str(run_id))))
        counts[name] = cur.fetchone()[0]
    staged = len(valid)
    rej = counts["stamp-flow-rejects"] + counts["reject-unknown-products"]
    eng.execute(f"UPDATE Etl.RunLog SET RowsStaged = {staged}, RowsRejected = {rej}, LinesInserted = {counts['insert-new-lines']}, "
                f"LinesUpdated = {counts['update-changed-lines']} WHERE RunLogId = {run_id};")
    return {"read": len(rows)}


def eng_sql(tsql: str) -> str:
    from labdb import transpile
    out = transpile(tsql)
    assert len(out) == 1, out
    return out[0]


def result_table(eng) -> list[list[str]]:
    """The DB-derived rows of c03-results.sql, computed with the same logic."""
    cols, rows = eng.query("""
        SELECT N'Rows staged' AS Item, CAST(RowsStaged AS varchar) AS Value FROM Etl.RunLog WHERE RunLogId = (SELECT MAX(RunLogId) FROM Etl.RunLog)
        UNION ALL SELECT N'Rows rejected', CAST(RowsRejected AS varchar) FROM Etl.RunLog WHERE RunLogId = (SELECT MAX(RunLogId) FROM Etl.RunLog)
        UNION ALL SELECT N'Lines inserted', CAST(LinesInserted AS varchar) FROM Etl.RunLog WHERE RunLogId = (SELECT MAX(RunLogId) FROM Etl.RunLog)
        UNION ALL SELECT N'Lines updated', CAST(LinesUpdated AS varchar) FROM Etl.RunLog WHERE RunLogId = (SELECT MAX(RunLogId) FROM Etl.RunLog)
        UNION ALL SELECT N'Lines in Sales.PartnerSales', CAST(COUNT(*) AS varchar) FROM Sales.PartnerSales""")
    return to_table(cols, rows)


def run_local() -> int:
    model = package_model()
    eng = local_setup()
    problems: list[str] = []
    try:
        print(f"package: {len(model['columns'])} columns, split rule: {model['rule']}")
        for run in RUNS:
            info = local_run(eng, model, run.file)
            got = result_table(eng)
            expected = [r for r in read_csv(EXPECTED_DIR / f"{run.key}.csv") if r[0] not in LOCAL_ONLY_SKIP]
            print(f"\n{run.key}: {run.title} ({info['read']} rows read)")
            print(format_table(got))
            problems += [f"{run.key}: {p}" for p in diff(expected, got)]
        rejects = eng.query("SELECT PartnerOrderRef, LineNumber, Reason FROM Etl.RejectedRows WHERE RunLogId = 1 ORDER BY PartnerOrderRef, LineNumber")[1]
        print("\nrejected in run 1:", rejects)
    finally:
        eng.close()
    print("\n" + ("local checks: the data flow model and the merge statements match expected/ on duckdb" if not problems
                  else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def use(engine: SqlServerEngine, db: str) -> None:
    res = engine.run_script(f"USE {db};")
    if res.errors:
        raise RuntimeError(res.errors[0])


def run_script_text(run: Run) -> str:
    """c02-run-package.sql with this run's logging level and file."""
    text = sql_text("c02-run-package")
    text, n1 = re.subn(r"DECLARE @LoggingLevel smallint = \d+;", f"DECLARE @LoggingLevel smallint = {run.logging_level};", text)
    text, n2 = re.subn(r"(DECLARE @InputFile nvarchar\(260\) = N')[^']*(';)", lambda m: m.group(1) + REMOTE_IN + run.file + m.group(2), text)
    assert n1 == 1 and n2 == 1
    return text


def run_sqlserver(engine: SqlServerEngine, setup: bool, deploy: bool, skip_runs: bool = False) -> int:
    if setup:
        for f in ("e00-reset.sql", "00-create-database.sql"):
            engine.run_file(SQL_DIR / f)
        use(engine, DB)
        engine.run_file(SQL_DIR / "01-schema-and-data.sql")
        engine.run_file(SQL_DIR / "e01-etl-objects.sql")
        print(f"setup: {DB} created with episode 5's tables and the ETL objects")
    if deploy:
        for f in ("c00-deploy-project.sql", "c01-environment.sql"):
            res = engine.run_script(sql_text(f))
            print(f"{f}: {'OK' if not res.errors else res.errors[0]}")
            if res.errors:
                return 1
            if res.columns:
                print(format_table(to_table(res.columns, res.rows)))
    if skip_runs:
        return 0
    failures = 0
    for run in RUNS:
        res = engine.run_script(run_script_text(run))
        print(f"\n{run.key}: {run.title}")
        if res.errors:
            print(f"  note: the run raised: {res.errors[0][:300]}")
        out = engine.run_script(sql_text("c03-results"))
        problems = [out.errors[0]] if out.errors else []
        if out.columns is None:
            problems.append("no result set")
        else:
            table = to_table(out.columns, out.rows)
            print(format_table(table))
            problems += diff(read_csv(EXPECTED_DIR / f"{run.key}.csv"), table)
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(RUNS) - failures}/{len(RUNS)} runs behaved as expected on sqlserver")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: reset and recreate the database first")
    ap.add_argument("--deploy", action="store_true", help="sqlserver: run c00 (deploy the .ispac) and c01 (environment) first")
    ap.add_argument("--skip-runs", action="store_true", help="sqlserver: stop after --setup/--deploy (do the runs by hand in SSMS)")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: tear-down (c99, then e00) and stop")
    a = ap.parse_args(argv)
    if a.engine == "duckdb":
        return run_local()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")
    eng = SqlServerEngine(conn_str)
    try:
        if a.reset_only:
            for f in ("c99-catalog-cleanup.sql", "e00-reset.sql"):
                res = eng.run_script(sql_text(f))
                print(f"{f}: {'OK' if not res.errors else res.errors[0]}")
            return 0
        return run_sqlserver(eng, a.setup, a.deploy, a.skip_runs)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
