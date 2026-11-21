"""Run the Synapse serverless T-SQL views on a laptop, over local parquet files.

This is NOT Synapse. It reads our own `sql/synapse/*.sql`, swaps the one `OPENROWSET(... FORMAT = 'PARQUET')` for
DuckDB's `read_parquet`, transpiles each view from T-SQL to DuckDB SQL with sqlglot and creates it in an in-memory
DuckDB database. Used for two things: the automated tests (the view logic runs against real parquet files) and the
training step, which then uses exactly the same silver/gold rules as the warehouse.
What it cannot prove: Synapse-specific behaviour (Entra passthrough, type mapping of the files Data Factory writes,
collation, query cost). Those are checked in the lab (demo.md).
"""
from __future__ import annotations

import pathlib
import re

import duckdb
import sqlglot
from sqlglot import exp

SQL_DIR = pathlib.Path(__file__).resolve().parents[2] / "sql" / "synapse"
VIEW_FILES = ("020-bronze.sql", "030-silver.sql", "040-gold.sql", "060-quality.sql")

_OPENROWSET = re.compile(
    r"OPENROWSET\s*\(\s*BULK\s+'(?P<path>[^']+)'\s*,\s*DATA_SOURCE\s*=\s*'lake'\s*,\s*FORMAT\s*=\s*'PARQUET'\s*\)",
    re.IGNORECASE)


def split_batches(text: str) -> list[str]:
    """Split a script on GO lines, like sqlcmd does, and drop empty batches."""
    batches = re.split(r"^\s*GO\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    return [b.strip() for b in batches if re.sub(r"--[^\n]*", "", b).strip()]


def transpile_view(batch: str, lake_root: pathlib.Path) -> tuple[str, str]:
    """Return (schema.name, duckdb CREATE VIEW statement) for one `CREATE OR ALTER VIEW` batch."""
    def _bulk(m: re.Match) -> str:
        pattern = (lake_root / m.group("path")).as_posix()
        return f"read_parquet('{pattern}', union_by_name = true)"

    rewritten = _OPENROWSET.sub(_bulk, batch)
    tree = sqlglot.parse_one(rewritten, read="tsql")
    if not isinstance(tree, exp.Create) or str(tree.args.get("kind")).upper() != "VIEW":
        raise ValueError("not a CREATE VIEW batch: " + batch[:60])
    name = f"{tree.this.args['db'].name}.{tree.this.name}"
    select = tree.expression.sql(dialect="duckdb")
    # datetime2(0) becomes TIMESTAMP(0) = TIMESTAMP_S, which DuckDB cannot cast to from nanosecond files; precision does not matter here
    select = re.sub(r"\bTIMESTAMP\(\d\)", "TIMESTAMP", select)
    return name, f"CREATE OR REPLACE VIEW {name} AS {select}"


class LocalWarehouse:
    """In-memory DuckDB with the bronze/silver/gold/quality views created from the T-SQL files."""

    def __init__(self, lake_root, sql_dir: pathlib.Path = SQL_DIR, extra_files: tuple[pathlib.Path, ...] = ()):
        self.lake_root = pathlib.Path(lake_root)
        self.con = duckdb.connect()
        for schema in ("bronze", "silver", "gold", "ref", "quality"):
            self.con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        self.views: dict[str, str] = {}
        files = [sql_dir / f for f in VIEW_FILES] + [pathlib.Path(f) for f in extra_files]
        for path in files:
            for batch in split_batches(path.read_text(encoding="utf-8")):
                name, ddl = transpile_view(batch, self.lake_root)
                self.con.execute(ddl)
                self.views[name] = ddl

    def query(self, sql: str):
        """Run a DuckDB query (not T-SQL) and return a pandas DataFrame."""
        return self.con.execute(sql).df()

    def close(self) -> None:
        self.con.close()
