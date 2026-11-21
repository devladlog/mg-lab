"""Tests for the Database Design & Normalization episode.

Two halves:
* the Python design step (normalize.py): 1NF split, dependency checks, conflict decisions, lossless join;
* the T-SQL design (01-schema.sql + generated 02-data.sql) running locally on DuckDB via sqlglot:
  the view rebuilds the export, one UPDATE fixes a city everywhere, and every constraint rejects bad data.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import normalize as nz  # noqa: E402
import tsql_runner as tr  # noqa: E402

SQL = ROOT / "src" / "sql"


@pytest.fixture(scope="module")
def flat():
    return nz.read_flat()


@pytest.fixture(scope="module")
def one_nf(flat):
    return nz.to_1nf(flat)


@pytest.fixture(scope="module")
def design(one_nf):
    return nz.normalize(one_nf)


@pytest.fixture()
def db():
    engine = tr.DuckDBEngine()
    tr.setup(engine)
    yield engine
    engine.close()


# ---------------------------------------------------------------- 1NF
def test_flat_export_has_a_repeating_group(flat):
    assert len(flat) == 16
    assert flat[0]["CourseCodes"] == "SQL101|SQL201"
    assert max(len(r["CourseCodes"].split("|")) for r in flat) == 3


def test_1nf_has_one_row_per_booking_line(one_nf):
    assert len(one_nf) == 23
    assert all("|" not in r["CourseCode"] for r in one_nf)
    assert nz.is_unique(one_nf, ("BookingRef", "CourseCode"))
    assert not nz.is_unique(one_nf, ("BookingRef",))


def test_1nf_rejects_lists_that_dont_line_up(flat):
    broken = [dict(flat[0], PricesPaid="450.00")]   # two codes, one price
    with pytest.raises(ValueError, match="B1001: list columns have different lengths"):
        nz.to_1nf(broken)


def test_prices_are_decimals_not_floats(one_nf):
    assert all(isinstance(r["PricePaid"], Decimal) for r in one_nf)
    assert sum(r["PricePaid"] for r in one_nf) == Decimal("11925.00")


# ---------------------------------------------------------------- dependencies
def test_partial_and_transitive_dependencies_are_classified():
    key = ("BookingRef", "CourseCode")
    assert nz.classify(("CourseCode",), key) == "partial: breaks 2NF"
    assert nz.classify(("BookingRef",), key) == "partial: breaks 2NF"
    assert nz.classify(("Company",), key) == "transitive: breaks 3NF"
    assert nz.classify(key, key) == "full (fine)"


def test_the_data_breaks_exactly_two_declared_dependencies(one_nf):
    broken = {(c["lhs"], c["rhs"]): c["conflicts"] for c in nz.check_design(one_nf) if not c["holds"]}
    assert broken == {
        (("Company",), "CompanyCity"): {("Contoso Ltd",): ["Oporto", "Porto"]},
        (("CourseCode",), "CourseTitle"): {("PBI200",): ["Power BI Data Modeling", "Power BI Data Modelling"]},
    }


def test_fd_violations_finds_conflicts_on_any_columns():
    rows = [{"a": 1, "b": "x"}, {"a": 1, "b": "y"}, {"a": 2, "b": "x"}]
    assert nz.fd_violations(rows, ("a",), "b") == {(1,): ["x", "y"]}
    assert nz.fd_violations(rows, ("b",), "a") == {("x",): [1, 2]}


def test_data_can_suggest_keys_but_not_prove_them(one_nf):
    keys = nz.candidate_keys(one_nf, nz.ONE_NF_COLUMNS)
    assert ("BookingRef", "CourseCode") in keys
    # in a sample this small, nonsense like (CustomerName, ListPrice) is unique too
    assert ("CustomerName", "ListPrice") in keys
    assert len(keys) == 16


# ---------------------------------------------------------------- 3NF
def test_conflicts_are_resolved_by_the_latest_booking(design):
    _, decisions = design
    by_column = {d["column"]: d for d in decisions}
    assert by_column["CompanyCity"]["kept"] == "Porto" and by_column["CompanyCity"]["rows_changed"] == 1
    assert by_column["CourseTitle"]["kept"] == "Power BI Data Modeling"


def test_3nf_tables_and_row_counts(design):
    tables, _ = design
    assert {t: len(v) for t, v in tables.items()} == {
        "Company": 4, "Customer": 7, "Course": 5, "Booking": 16, "BookingLine": 23}


def test_every_declared_dependency_holds_inside_its_table(design):
    tables, _ = design
    assert nz.is_unique(tables["Company"], ("CompanyName",))
    assert nz.is_unique(tables["Customer"], ("Email",))
    assert nz.is_unique(tables["Course"], ("CourseCode",))
    assert nz.is_unique(tables["Booking"], ("BookingRef",))
    assert nz.is_unique(tables["BookingLine"], ("BookingRef", "CourseCode"))


def test_decomposition_is_lossless(one_nf, design):
    tables, _ = design
    resolved, _ = nz.resolve(one_nf)
    expected = sorted(resolved, key=lambda r: (r["BookingRef"], r["CourseCode"]))
    assert nz.rebuild(tables) == expected


def test_redundancy_removed_contoso_city_stored_once(one_nf, design):
    tables, _ = design
    assert sum(r["Company"] == "Contoso Ltd" for r in one_nf) == 7     # 7 copies in the export
    assert sum(c["CompanyName"] == "Contoso Ltd" for c in tables["Company"]) == 1


def test_generated_data_script_is_up_to_date(design):
    tables, _ = design
    assert (SQL / "02-data.sql").read_text(encoding="utf-8") == nz.to_tsql(tables)


def test_report_mentions_the_decisions(flat):
    text = nz.report(flat)
    assert "kept 'Porto' (latest booking)" in text
    assert "lossless join (rebuild == resolved 1NF): True" in text


# ---------------------------------------------------------------- the T-SQL design, run locally
def test_every_sql_file_parses_with_the_tsql_dialect():
    import sqlglot

    for f in sorted(SQL.glob("*.sql")):
        for batch in tr.split_batches(f.read_text(encoding="utf-8")):
            sqlglot.parse(batch, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)


def test_schema_loads_with_the_expected_row_counts(db):
    assert tr.row_counts(db) == {"Company": 4, "Customer": 7, "Course": 5, "Booking": 16, "BookingLine": 23}


@pytest.mark.parametrize("path", tr.query_files(), ids=lambda p: p.stem)
def test_query_matches_expected_csv(db, path):
    assert tr.diff(tr.read_csv(ROOT / "expected" / f"{path.stem}.csv"), tr.to_table(*tr.run_query(db, path))) == []


def test_view_rebuilds_the_resolved_export(db, one_nf):
    cols, rows = tr.run_query(db, SQL / "q01-bookings-rebuilt.sql")
    from_db = [dict(zip(cols, r)) for r in rows]
    resolved, _ = nz.resolve(one_nf)
    expected = sorted(resolved, key=lambda r: (r["BookingRef"], r["CourseCode"]))
    assert [{k: tr.normalize(v) for k, v in r.items()} for r in from_db] == \
           [{k: tr.normalize(v) for k, v in r.items()} for r in expected]


def test_list_price_and_price_paid_both_needed(db, one_nf):
    cols, rows = tr.run_query(db, SQL / "q02-revenue-by-course.sql")
    data = {r[0]: dict(zip(cols, r)) for r in rows}
    for code, row in data.items():
        lines = [r for r in one_nf if r["CourseCode"] == code]
        assert row["Paid"] == sum(r["PricePaid"] for r in lines)
        assert row["Discount"] == row["AtListPrice"] - row["Paid"]
    assert sum(r["Discount"] for r in data.values()) == Decimal("425.00")


def test_one_update_moves_contoso_everywhere_then_rolls_back(db):
    cols, rows = tr.run_query(db, SQL / "q03-update-once.sql")
    contoso = dict(zip(cols, next(r for r in rows if r[0] == "Contoso Ltd")))
    assert contoso == {"Company": "Contoso Ltd", "CompanyCity": "Matosinhos", "Bookings": 5, "BookingLines": 7}
    assert db.run("SELECT City FROM Training.Company WHERE CompanyName = 'Contoso Ltd';")[1] == [("Porto",)]


EXPECTED_REJECTIONS = [
    ("1.", "unique constraint"),
    ("2.", "foreign key constraint"),
    ("3.", "foreign key constraint"),
    ("4.", "primary key constraint"),
    ("5.", "CHECK constraint failed"),
    ("6.", "still referenced by a foreign key"),
]


def test_every_bad_write_is_rejected_by_the_right_constraint(db):
    results = tr.check_constraints(db)
    assert len(results) == 6, results            # a 7th entry would mean the row counts moved
    for (title, ok, msg), (prefix, phrase) in zip(results, EXPECTED_REJECTIONS):
        assert ok, title
        assert title.startswith(prefix)
        assert phrase in msg, (title, msg)


def test_without_the_unique_constraint_the_duplicate_gets_in(db):
    """The constraint, not luck, keeps the second Alex out."""
    db.con.execute("CREATE TABLE loose AS SELECT * FROM Training.Customer")
    db.con.execute("INSERT INTO loose VALUES (8, 'alex.demo@contoso.example', 'Alex Duplicate', 2)")
    assert db.con.execute("SELECT COUNT(*) FROM loose WHERE Email = 'alex.demo@contoso.example'").fetchone()[0] == 2


def test_runner_cli_end_to_end(capsys):
    assert tr.main([]) == 0
    out = capsys.readouterr().out
    assert "3/3 queries match expected/ on duckdb" in out
    assert "6/6 constraint checks behaved on duckdb" in out


# ---------------------------------------------------------------- the harness
def test_transpile_maps_identity_and_skips_identity_insert():
    out = tr.transpile("CREATE TABLE S.T (Id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_T PRIMARY KEY, N nvarchar(5));")
    assert out[0] == "CREATE OR REPLACE SEQUENCE seq_S_T_Id START 1000"
    assert "DEFAULT NEXTVAL('seq_S_T_Id')" in out[1] and "IDENTITY" not in out[1]
    assert tr.transpile("SET IDENTITY_INSERT S.T ON;") == []
    assert tr.transpile("SET IDENTITY_INSERT S.T OFF;") == []


def test_sqlserver_engine_needs_a_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        tr.main(["--engine", "sqlserver"])
