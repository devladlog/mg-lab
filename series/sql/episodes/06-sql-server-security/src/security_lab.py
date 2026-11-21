"""SQL Server security lab runner: principals, ownership chaining, SQL injection, module signing,
row-level security and dynamic data masking, on episode 5's ContosoBikesApp database.

* ``sqlserver`` - the demo. Resets the security objects, reloads episode 5's tables, functions and procedures,
  adds this episode's procedures, users, roles, grants and mask, then runs eight step files. Every step
  impersonates a database user (EXECUTE AS USER ... REVERT), records each attempt as a row, and its last
  result set is compared with expected/. After each step the runner makes sure the session is back to its
  own user.
* ``duckdb``    - the local check (no server): the injection mechanics and the masking inference, executed.
  It builds the SQL text exactly as the two search procedures do (string concatenation vs fixed text plus a
  bound parameter), runs it on the same data, and runs the analyst's LIKE guesses. Permissions, signing,
  RLS and masking themselves need SQL Server.

    python src/security_lab.py                                  # duckdb: injection + inference counts
    python src/security_lab.py --engine sqlserver --setup       # needs SQL_CONNECTION_STRING
    python src/security_lab.py --engine sqlserver --reset-only  # tear-down: removes this episode's objects
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
                   to_table, transpile)

SQL_DIR = HERE / "sql"
EXPECTED_DIR = HERE.parent / "expected"
RESET_FILE = "10-reset-security.sql"
SETUP_FILES = [RESET_FILE, "01-schema-and-data.sql", "02-functions.sql", "03-procedures.sql",
               "11-app-procedures.sql", "12-principals-and-grants.sql", "13-dynamic-data-masking.sql"]
APP_PROCS = "11-app-procedures.sql"


@dataclass
class Step:
    key: str                                   # src/sql/<key>.sql and expected/<key>.csv
    title: str
    before: list[str] = field(default_factory=list)   # files run (as the runner's login) before the step
    checks: list[str] = field(default_factory=lambda: ["error: none"])


STEPS = [
    Step("s01-least-privilege", "app user: procedures yes, tables no"),
    Step("s02-injection-unsafe", "concatenated SQL: a name filter that returns everyone"),
    Step("s03-dynamic-sql-breaks-chain", "parameterized search, unsigned: the ownership chain stops at dynamic SQL"),
    Step("s04-signed-search", "signed with a certificate: works, and the payload is just text",
         before=["14-sign-search-procedure.sql"]),
    Step("s05-row-level-security", "row-level security: same procedure, different rows",
         before=["15-row-level-security.sql"]),
    Step("s06-rls-place-order", "row-level security inside a procedure that writes"),
    Step("s07-masking", "dynamic data masking: what the analyst sees"),
    Step("s08-masking-inference", "masking is not access control: WHERE still sees the real value"),
]


def sql_text(key_or_file: str) -> str:
    name = key_or_file if key_or_file.endswith(".sql") else f"{key_or_file}.sql"
    return (SQL_DIR / name).read_text(encoding="utf-8")


def evaluate(check: str, res: ScriptResult) -> str | None:
    kind, _, arg = check.partition(":")
    if kind == "error" and arg.strip() == "none":
        return None if not res.errors else f"unexpected error: {res.errors[0][:200]}"
    raise ValueError(f"unknown check: {check}")


# ---------------------------------------------------------------- the injection, executed locally
_TOKEN = re.compile(r"\s*(?:(?P<lit>N?'(?:[^']|'')*')|(?P<plus>\+)|(?P<qn>QUOTENAME\(\s*@(?P<qvar>\w+)\s*\))"
                    r"|(?P<var>@\w+)|(?P<end>;))", re.IGNORECASE)


def tsql_literal(token: str) -> str:
    """N'it''s' -> it's"""
    return token[token.index("'") + 1:-1].replace("''", "'")


def eval_concat(expr: str, variables: dict[str, str]) -> str:
    """Evaluate a T-SQL string expression made of literals, @variables, QUOTENAME(@variable) and +.
    That's all the two search procedures use to build their SQL text."""
    out, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip():
                raise ValueError(f"can't evaluate: {expr[pos:pos + 40]!r}")
            break
        pos = m.end()
        if m.group("lit"):
            out.append(tsql_literal(m.group("lit")))
        elif m.group("qn"):
            out.append("[" + variables[m.group("qvar")].replace("]", "]]") + "]")
        elif m.group("var"):
            out.append(variables[m.group("var")[1:]])
        elif m.group("end"):
            break
    return "".join(out)


def sql_builder(procedure: str) -> str:
    """The expression after `DECLARE @sql nvarchar(max) =` in a procedure of 11-app-procedures.sql (the tests
    check it is the same text Microsoft's parser finds)."""
    body = sql_text(APP_PROCS).split(f"CREATE OR ALTER PROCEDURE {procedure}\n", 1)[1].split("\nGO", 1)[0]
    start = re.search(r"DECLARE @sql nvarchar\(max\) =\s*", body).end()
    pos, in_lit = start, False
    while pos < len(body):          # the expression ends at the first ; outside a string literal
        ch = body[pos]
        if ch == "'":
            in_lit = not in_lit
        elif ch == ";" and not in_lit:
            break
        pos += 1
    return body[start:pos].strip()


def step_inputs(key: str) -> list[str]:
    """The @NamePrefix values a step file passes, in order."""
    return [tsql_literal(t) for t in re.findall(r"@NamePrefix = (N'(?:[^']|'')*')", sql_text(key))]


def local_search(eng: DuckDBEngine, procedure: str, name_prefix: str) -> int:
    sql = eval_concat(sql_builder(procedure), {"NamePrefix": name_prefix, "SortBy": "CustomerId"})
    if procedure.endswith("_Unsafe"):                       # EXEC (@sql): the input is now part of the code
        return len(eng.query(sql)[1])
    # sp_executesql @sql, N'@prefix nvarchar(100)', @prefix = @NamePrefix: the input stays a value.
    # DuckDB spells string concatenation || and named parameters $name.
    duck = transpile(sql)[0].replace("$prefix + N'%'", "$prefix || '%'")
    return len(eng.con.execute(duck, {"prefix": name_prefix}).fetchall())


def local_guesses(eng: DuckDBEngine) -> list[tuple[str, int]]:
    """The analyst's LIKE guesses from s08, run on the real (unmasked) data, which is what SQL Server does."""
    out = []
    for guess, pred in re.findall(r"SELECT \d+, N'([^']*)',\s+COUNT\(\*\) (FROM Sales\.Customers WHERE Email LIKE N'[^']*');",
                                  sql_text("s08-masking-inference")):
        out.append((guess, eng.query(f"SELECT COUNT(*) {pred}")[1][0][0]))
    return out


def expected_column(key: str, column: str) -> list[str]:
    table = read_csv(EXPECTED_DIR / f"{key}.csv")
    i = table[0].index(column)
    return [r[i] for r in table[1:]]


def run_local() -> int:
    eng = DuckDBEngine()
    problems = []
    try:
        eng.run_file(SQL_DIR / "01-schema-and-data.sql")
        print("setup: 01-schema-and-data.sql loaded (duckdb)")
        for key, proc in (("s02-injection-unsafe", "Sales.usp_SearchCustomers_Unsafe"),
                          ("s04-signed-search", "Sales.usp_SearchCustomers")):
            inputs = step_inputs(key)
            got = [local_search(eng, proc, i) for i in inputs]
            print(f"\n{key}: {proc}")
            if proc.endswith("_Unsafe"):
                print("  SQL text built for the payload: "
                      + eval_concat(sql_builder(proc), {"NamePrefix": inputs[-1]}))
            print(format_table([["Input", "RowsReturned"]] + [[i, str(n)] for i, n in zip(inputs, got)]))
            want = expected_column(key, "RowsReturned")
            if [str(n) for n in got] != want:
                problems.append(f"{key}: rows {got}, expected {want}")
        guesses = local_guesses(eng)
        print("\ns08-masking-inference: the analyst's guesses on the real values")
        print(format_table([["Guess", "RowsMatched"]] + [[g, str(n)] for g, n in guesses]))
        if [[g, str(n)] for g, n in guesses] != read_csv(EXPECTED_DIR / "s08-masking-inference.csv")[1:]:
            problems.append("s08-masking-inference: counts differ from expected/")
    finally:
        eng.close()
    print("\n" + ("local checks: injection and inference counts match expected/ on duckdb" if not problems
                  else "local checks FAILED: " + "; ".join(problems)))
    return 1 if problems else 0


# ---------------------------------------------------------------- SQL Server
def current_user(engine: SqlServerEngine) -> str:
    res = engine.run_script("SELECT USER_NAME() AS CurrentUser;")
    return res.rows[0][0]


def back_to(engine: SqlServerEngine, user: str) -> None:
    """A step that failed between EXECUTE AS and REVERT would leave the session impersonating: undo it."""
    for _ in range(5):
        if current_user(engine) == user:
            return
        engine.run_script("REVERT;")
    raise RuntimeError(f"session is not back to {user} after REVERT")


def run_sqlserver(engine: SqlServerEngine, steps: list[Step], setup: bool) -> int:
    me = current_user(engine)
    if setup:
        for f in SETUP_FILES:
            engine.run_file(SQL_DIR / f)
        print(f"setup: security reset; episode 5 objects, app procedures, users, roles, grants and the email mask "
              f"created (runner user: {me})")
    failures = 0
    for step in steps:
        for f in step.before:
            engine.run_file(SQL_DIR / f)
            print(f"\nran {f}")
        res = engine.run_script(sql_text(step.key))
        back_to(engine, me)
        print(f"\n{step.key}: {step.title}")
        problems = [f"{c}: {why}" for c in step.checks if (why := evaluate(c, res))]
        for c in step.checks:
            print(f"  check {c:<20} {'OK' if not any(p.startswith(c + ':') for p in problems) else 'FAILED'}")
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
    ap.add_argument("--setup", action="store_true", help="sqlserver: reset and recreate everything first")
    ap.add_argument("--reset-only", action="store_true", help="sqlserver: run 10-reset-security.sql and stop")
    ap.add_argument("--step", action="append", help="run only these steps (repeatable; they build on each other)")
    a = ap.parse_args(argv)

    steps = [s for s in STEPS if not a.step or s.key in a.step]
    if a.step and len(steps) != len(a.step):
        ap.error(f"unknown step; choose from {[s.key for s in STEPS]}")
    if a.engine == "duckdb":
        return run_local()
    conn_str = os.environ.get("SQL_CONNECTION_STRING")
    if not conn_str:
        ap.error("set SQL_CONNECTION_STRING for --engine sqlserver")
    eng = SqlServerEngine(conn_str)
    try:
        if a.reset_only:
            eng.run_file(SQL_DIR / RESET_FILE)
            print("reset: this episode's security objects removed (episode 5's tables and procedures kept)")
            return 0
        return run_sqlserver(eng, steps, a.setup)
    finally:
        eng.close()


if __name__ == "__main__":
    sys.exit(main())
