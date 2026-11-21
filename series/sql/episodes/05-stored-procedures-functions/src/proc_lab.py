"""Stored procedures & functions lab runner: the same T-SQL files, two engines.

* ``sqlserver`` - the demo. Loads the database, creates the functions and procedures, then runs every step
  file the way SSMS would (batch by batch, carrying on after a failed batch) and checks it: the rows against
  expected/, the error each batch raised ("error: CK_Products_StockQty"), and for the function steps the
  ACTUAL plan ("plan: inlined" = no UserDefinedFunction node in the plan XML).
* ``duckdb``    - the local check (tests, CI, no server): loads the same data and runs the function steps
  with the functions inlined by hand, from the definitions in 02-functions.sql, which is what SQL Server's
  scalar UDF inlining does. Procedures, errors and plans need SQL Server.

    python src/proc_lab.py                                  # duckdb: data + the three function queries
    python src/proc_lab.py --engine sqlserver --setup       # needs SQL_CONNECTION_STRING
    python src/proc_lab.py --engine sqlserver --step d03-naive-out-of-stock
    python src/proc_lab.py --write-expected                 # regenerate expected/ for the duckdb steps
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
from labdb import (DuckDBEngine, ScriptResult, SqlServerEngine, diff, format_table, read_csv,  # noqa: E402
                   to_table, write_csv)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
SETUP_FILES = ["01-schema-and-data.sql", "02-functions.sql", "03-procedures.sql"]
FUNCTIONS_FILE = "02-functions.sql"


@dataclass
class Step:
    key: str                      # src/sql/<key>.sql and expected/<key>.csv
    title: str
    checks: list[str] = field(default_factory=list)
    local: bool = False           # can the local DuckDB check run it?


STEPS = [
    Step("r01-inlining-catalog", "which functions can SQL Server inline?", ["error: none"]),
    Step("r02a-order-totals", "order totals through the scalar UDF", ["error: none", "plan: inlined"], local=True),
    Step("r02b-order-totals-no-inlining", "same query, inlining switched off",
         ["error: none", "plan: not inlined"], local=True),
    Step("r03-customer-orders-apply", "inline TVF with CROSS APPLY", ["error: none"], local=True),
    Step("d01-place-order", "safe procedure, a good order", ["error: none"]),
    Step("d02-unknown-customer", "safe procedure, THROW 50001 (caught in the script)", ["error: none"]),
    Step("d03-naive-out-of-stock", "NAIVE procedure, out of stock", ["error: CK_Products_StockQty"]),
    Step("d04-safe-out-of-stock", "safe procedure, out of stock", ["error: CK_Products_StockQty"]),
]


def sql_text(key_or_file: str) -> str:
    name = key_or_file if key_or_file.endswith(".sql") else f"{key_or_file}.sql"
    return (SQL_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- checks
def evaluate(check: str, res: ScriptResult) -> str | None:
    """None when the check passes, otherwise the reason it failed."""
    kind, _, arg = check.partition(":")
    arg = arg.strip()
    if kind == "error":
        if arg == "none":
            return None if not res.errors else f"unexpected error: {res.errors[0][:160]}"
        if not res.errors:
            return f"expected an error mentioning {arg}, the script raised none"
        return None if any(arg in e for e in res.errors) else f"error doesn't mention {arg}: {res.errors[0][:160]}"
    if kind == "plan":
        if not res.plans:
            return "no actual plan captured"
        udf = any("<UserDefinedFunction" in p for p in res.plans)
        if arg == "inlined":
            return None if not udf else "the plan still calls the function (UserDefinedFunction node)"
        if arg == "not inlined":
            return None if udf else "no UserDefinedFunction node: the function was inlined"
    raise ValueError(f"unknown check: {check}")


# ---------------------------------------------------------------- local inlining (what SQL Server does for us)
_FUNC = re.compile(
    r"CREATE\s+OR\s+ALTER\s+FUNCTION\s+(?P<name>[\w.]+)\s*\((?P<params>.*?)\)\s*RETURNS\s+(?P<returns>\w+)"
    r".*?\bAS\b\s*(?P<body>.*?)^GO\s*$", re.IGNORECASE | re.DOTALL | re.MULTILINE)


@dataclass
class FunctionDef:
    name: str
    params: list[str]
    kind: str            # "scalar" or "inline"
    text: str            # the RETURN expression (scalar) or the SELECT (inline TVF)


def parse_functions(script: str) -> dict[str, FunctionDef]:
    """The scalar UDFs with a single RETURN and the inline TVFs of a script (tests compare with ScriptDom)."""
    out = {}
    for m in _FUNC.finditer(script):
        params = re.findall(r"@(\w+)", m.group("params"))
        body = m.group("body").strip()
        if m.group("returns").upper() == "TABLE":
            sel = re.match(r"RETURN\s*(.*?);?\s*$", body, re.DOTALL | re.IGNORECASE)
            out[m.group("name")] = FunctionDef(m.group("name"), params, "inline", sel.group(1).strip())
        else:
            ret = re.findall(r"\bRETURN\s+(.*?);", body, re.DOTALL | re.IGNORECASE)
            if len(ret) == 1:
                out[m.group("name")] = FunctionDef(m.group("name"), params, "scalar", ret[0].strip())
    return out


def _substitute(text: str, params: list[str], args: list[str]) -> str:
    for p, a in zip(params, args):
        text = re.sub(rf"@{p}\b", f"({a.strip()})", text)
    return text


def inline_functions(query: str, functions: dict[str, FunctionDef]) -> str:
    """Replace each call by the function's own body, inline TVFs first (their bodies call the scalar UDF)."""
    for f in sorted(functions.values(), key=lambda f: f.kind != "inline"):
        pattern = re.compile(rf"{re.escape(f.name)}\s*\(([^()]*)\)", re.IGNORECASE)
        while m := pattern.search(query):
            args = [a for a in m.group(1).split(",")] if m.group(1).strip() else []
            body = _substitute(f.text, f.params, args)
            query = query[:m.start()] + f"({body})" + query[m.end():]
    return query


def strip_use_hint(query: str) -> str:
    """OPTION (USE HINT(...)) changes the plan, not the result; sqlglot can't parse USE HINT, so the local
    check drops the clause before transpiling."""
    return re.sub(r"\bOPTION\s*\((?:[^()]|\([^()]*\))*\)", "", query, flags=re.IGNORECASE)


def local_query(key: str) -> str:
    functions = parse_functions(sql_text(FUNCTIONS_FILE))
    return strip_use_hint(inline_functions(sql_text(key), functions))


# ---------------------------------------------------------------- runs
def run_local(steps: list[Step], write_expected: bool = False) -> int:
    eng = DuckDBEngine()
    failures = 0
    try:
        eng.run_file(SQL_DIR / SETUP_FILES[0])
        print("setup: 01-schema-and-data.sql loaded (duckdb)")
        for step in steps:
            if not step.local:
                print(f"\n{step.key}: SQL Server only (procedure, catalog view, error or plan) - skipped")
                continue
            cols, rows = eng.query(local_query(step.key))
            table = to_table(cols, rows)
            print(f"\n{step.key}: {step.title}\n{format_table(table)}")
            if write_expected:
                write_csv(EXPECTED_DIR / f"{step.key}.csv", table)
                print(f"wrote expected/{step.key}.csv")
                continue
            problems = diff(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)
            print("result: identical to expected/" if not problems else "result: " + "; ".join(problems))
            failures += bool(problems)
    finally:
        eng.close()
    ran = len([s for s in steps if s.local])
    print(f"\n{ran - failures}/{ran} local steps match expected/ on duckdb")
    return 1 if failures else 0


def run_sqlserver(engine: SqlServerEngine, steps: list[Step], setup: bool) -> int:
    if setup:
        for f in SETUP_FILES:
            engine.run_file(SQL_DIR / f)
        print("setup: tables, data, functions and procedures (re)created")
    failures = 0
    for step in steps:
        wants_plan = any(c.startswith("plan:") for c in step.checks)
        res = engine.run_script(sql_text(step.key), plans=wants_plan)
        print(f"\n{step.key}: {step.title}")
        for e in res.errors:
            print(f"  error raised: {e.splitlines()[0][:200]}")
        problems = [f"{c}: {why}" for c in step.checks if (why := evaluate(c, res))]
        for c in step.checks:
            print(f"  check {c:<32} {'OK' if not any(p.startswith(c + ':') for p in problems) else 'FAILED'}")
        if res.columns is None:
            problems.append("no result set")
        else:
            table = to_table(res.columns, res.rows)
            print(format_table(table))
            problems += diff(read_csv(EXPECTED_DIR / f"{step.key}.csv"), table)
        print("  => OK" if not problems else "  => " + "; ".join(problems))
        failures += bool(problems)
    print(f"\n{len(steps) - failures}/{len(steps)} steps behaved as expected on sqlserver")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["duckdb", "sqlserver"], default="duckdb")
    ap.add_argument("--setup", action="store_true", help="sqlserver: (re)create tables, data, functions, procedures")
    ap.add_argument("--step", action="append", help="run only these steps (repeatable)")
    ap.add_argument("--write-expected", action="store_true", help="duckdb: rewrite expected/ for the local steps")
    a = ap.parse_args(argv)

    steps = [s for s in STEPS if not a.step or s.key in a.step]
    if a.step and len(steps) != len(a.step):
        ap.error(f"unknown step; choose from {[s.key for s in STEPS]}")
    if a.engine == "duckdb":
        return run_local(steps, a.write_expected)
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")
    if a.step and not a.setup and any(s.key.startswith("d") for s in steps):
        print("note: the d* steps expect the data as --setup leaves it; run them in order after --setup")
    eng = SqlServerEngine(conn_str)
    try:
        return run_sqlserver(eng, steps, a.setup)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
