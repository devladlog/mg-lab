"""The Synapse serverless views, run over real parquet files through the local DuckDB runner (see analytics/localsql.py)."""
import logging
import pathlib
import re

import pandas as pd
import pytest
import sqlglot

from analytics import SLA_DAYS, synthetic as syn
from analytics.localsql import SQL_DIR, LocalWarehouse, _OPENROWSET, split_batches

ALL_SQL = sorted((pathlib.Path(__file__).resolve().parents[1] / "sql").glob("*/*.sql"))


@pytest.mark.parametrize("path", ALL_SQL, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_script_parses_as_tsql(path):
    text = re.sub(r"\$\((\w+)\)", r"\1", path.read_text(encoding="utf-8"))
    text = _OPENROWSET.sub("some_table", text)
    for batch in split_batches(text):
        logging.getLogger("sqlglot").setLevel(logging.CRITICAL)
        assert sqlglot.parse(batch, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)


def test_each_view_is_the_first_statement_of_its_batch():
    """Learn: CREATE VIEW must be the first statement in a query batch."""
    for f in sorted(SQL_DIR.glob("0[2-6]0-*.sql")):
        for batch in split_batches(f.read_text(encoding="utf-8")):
            body = re.sub(r"--[^\n]*\n", "", batch).strip()
            assert body.upper().startswith("CREATE OR ALTER VIEW"), (f.name, body[:40])


def test_only_the_bronze_view_knows_where_the_files_are():
    for f in SQL_DIR.glob("*.sql"):
        has = "OPENROWSET" in f.read_text(encoding="utf-8").upper()
        assert has == (f.name == "020-bronze.sql"), f.name


def test_files_are_read_through_the_data_source_with_no_credentials_or_keys_in_sql():
    text = "\n".join(f.read_text(encoding="utf-8") for f in SQL_DIR.glob("*.sql"))
    assert "DATA_SOURCE = 'lake'" in text
    for forbidden in ("SECRET", "SAS", "IDENTITY =", "?sv=", "AccountKey"):
        assert forbidden.lower() not in text.lower().replace("sasl", ""), forbidden


def test_database_uses_a_utf8_collation():
    assert "COLLATE Latin1_General_100_BIN2_UTF8" in (SQL_DIR / "000-database.sql").read_text(encoding="utf-8")


def test_bronze_keeps_every_version(warehouse, history):
    n = warehouse.query("SELECT COUNT(*) AS n FROM bronze.PurchaseRequest")["n"][0]
    first, second = syn.delta(history, None, syn.T1), syn.delta(history, syn.T1, syn.T2)
    assert n == len(first) + len(second) + 4


def test_silver_keeps_the_latest_version_of_each_request(warehouse, history):
    silver = warehouse.query("SELECT * FROM silver.PurchaseRequest WHERE RequestId < 9000").set_index("RequestId").sort_index()
    final = syn.snapshot(history, syn.T2).set_index("RequestId").sort_index()
    assert list(silver.index) == list(final.index)
    assert (silver["Status"] == final["Status"]).all()
    assert (pd.to_datetime(silver["ModifiedOn"]) == final["ModifiedOn"]).all()
    # the interesting rows: open at the first load, decided by the second
    reopened = set(syn.delta(history, None, syn.T1).query("Status == 'Submitted'")["RequestId"]) & \
        set(syn.delta(history, syn.T1, syn.T2)["RequestId"])
    assert len(reopened) > 5
    assert (silver.loc[sorted(reopened), "Status"] != "Submitted").all()


def test_silver_flags_the_four_defects_with_the_right_reason(warehouse):
    s = warehouse.query("SELECT RequestId, RejectReason, IsValid FROM silver.PurchaseRequest WHERE IsValid = 0").set_index("RequestId")
    assert s["RejectReason"].to_dict() == {
        9001: "NonPositiveAmount", 9002: "UnknownDepartment", 9003: "ApprovedBeforeSubmitted", 9004: "UnknownStatus"}


def test_gold_fact_excludes_invalid_rows_and_computes_cycle_and_sla(warehouse, history):
    fact = warehouse.query("SELECT * FROM gold.FactPurchaseRequest")
    assert not set(fact["RequestId"]) & {9001, 9002, 9003, 9004}
    ok = fact[fact["Status"] == "Approved"]
    expected = (pd.to_datetime(ok["ApprovedDate"]) - pd.to_datetime(ok["SubmittedDate"])).dt.days
    assert (ok["CycleDays"] == expected).all()
    assert (ok["SlaBreached"] == (ok["CycleDays"] > SLA_DAYS).astype(int)).all()
    assert fact.loc[fact["Status"] != "Approved", "SlaBreached"].isna().all()


def test_sla_in_sql_is_the_sla_in_python():
    assert f"> {SLA_DAYS} THEN 1" in (SQL_DIR / "040-gold.sql").read_text(encoding="utf-8")


def test_weekday_is_monday_zero_whatever_the_server_language(warehouse):
    fact = warehouse.query("SELECT SubmittedDate, SubmittedWeekday FROM gold.FactPurchaseRequest")
    assert (pd.to_datetime(fact["SubmittedDate"]).dt.weekday == fact["SubmittedWeekday"]).all()


def test_department_monthly_adds_up_to_the_fact(warehouse):
    m = warehouse.query("SELECT SUM(Requests) AS r, SUM(Spend) AS s FROM gold.DepartmentMonthly").iloc[0]
    f = warehouse.query("SELECT COUNT(*) AS r, SUM(Amount) AS s FROM gold.FactPurchaseRequest").iloc[0]
    assert m["r"] == f["r"] and m["s"] == pytest.approx(f["s"])


def test_every_fact_department_exists_in_the_dimension(warehouse):
    orphans = warehouse.query("SELECT COUNT(*) AS n FROM gold.FactPurchaseRequest f "
                              "LEFT JOIN gold.DimDepartment d ON d.DepartmentKey = f.DepartmentKey WHERE d.DepartmentKey IS NULL")
    assert orphans["n"][0] == 0


def test_quality_report_counts_the_four_errors_and_nothing_else(warehouse):
    q = warehouse.query("SELECT * FROM quality.CheckResult")
    errors = q[q["Severity"] == "error"]
    assert errors["RowTotal"].sum() == 4
    assert set(errors["CheckName"]) == {"rejected: NonPositiveAmount", "rejected: UnknownDepartment",
                                         "rejected: ApprovedBeforeSubmitted", "rejected: UnknownStatus"}
    info = q[q["Severity"] == "info"].set_index("CheckName")["RowTotal"]
    assert info["bronze row versions"] > info["distinct requests"]


def test_clean_data_has_no_errors(tmp_path, history):
    syn.write_bronze(syn.delta(history, None, syn.T1), tmp_path, "2026-10-31", "run1")
    wh = LocalWarehouse(tmp_path)
    try:
        q = wh.query("SELECT * FROM quality.CheckResult WHERE Severity = 'error'")
    finally:
        wh.close()
    assert len(q) == 0
