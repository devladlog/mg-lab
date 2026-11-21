"""The Data Factory pipeline's own queries, taken from adf/pipeline-incremental.json and run against SQLite.

SQLite stands in for Azure SQL only to execute the SQL text. What is checked is the logic of the pattern: the window is
(old watermark, new watermark], nothing is copied twice, nothing is lost, and an empty source leaves the watermark alone.
"""
import json
import pathlib
import re
import sqlite3

import pandas as pd

from analytics import synthetic as syn

ADF = pathlib.Path(__file__).resolve().parents[1] / "adf"
PIPELINE = json.loads((ADF / "pipeline-incremental.json").read_text())
ACT = {a["name"]: a for a in PIPELINE["activities"]}


def render(expr: str, old=None, new=None, table="dbo.PurchaseRequests") -> str:
    """Evaluate the three @{...} string interpolations the pipeline uses."""
    out = expr.replace("@{pipeline().parameters.TableName}", table)
    if old is not None:
        out = out.replace("@{activity('LookupOldWatermark').output.firstRow.WatermarkValue}", old)
    if new is not None:
        out = out.replace("@{activity('LookupNewWatermark').output.firstRow.NewWatermark}", new)
    return out


def sqlite_dialect(sql: str) -> str:
    sql = re.sub(r"\b(FROM|JOIN)\s+dbo\.", r"\1 ", sql)       # table names only; the string literal 'dbo.PurchaseRequests' stays
    return re.sub(r"\b(FROM|JOIN)\s+etl\.", r"\1 etl_", sql)


class Source:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE PurchaseRequests (RequestId INTEGER PRIMARY KEY, DepartmentCode TEXT, Category TEXT, "
                         "VendorName TEXT, Amount REAL, Currency TEXT, Status TEXT, SubmittedOn TEXT, ApprovedOn TEXT, ModifiedOn TEXT)")
        self.con.execute("CREATE TABLE etl_Watermark (TableName TEXT PRIMARY KEY, WatermarkValue TEXT)")
        self.con.execute("INSERT INTO etl_Watermark VALUES ('dbo.PurchaseRequests', '1900-01-01T00:00:00')")

    def load(self, df: pd.DataFrame):
        d = df.copy()
        for c in ("SubmittedOn", "ApprovedOn", "ModifiedOn"):
            d[c] = d[c].dt.strftime("%Y-%m-%dT%H:%M:%S").where(d[c].notna(), None)
        self.con.executemany(
            "INSERT OR REPLACE INTO PurchaseRequests VALUES (?,?,?,?,?,?,?,?,?,?)",
            [tuple(None if pd.isna(v) else v for v in row) for row in d[syn.COLUMNS].itertuples(index=False, name=None)])

    def one(self, sql: str):
        return self.con.execute(sqlite_dialect(sql)).fetchone()

    def run_pipeline(self) -> pd.DataFrame:
        """Lookup, Lookup, Copy, StoredProcedure: exactly the activity order in the JSON."""
        old = self.one(render(ACT["LookupOldWatermark"]["typeProperties"]["source"]["sqlReaderQuery"]))[0]
        new = self.one(render(ACT["LookupNewWatermark"]["typeProperties"]["source"]["sqlReaderQuery"]))[0]
        copy_sql = render(ACT["CopyDeltaToBronze"]["typeProperties"]["source"]["sqlReaderQuery"], old, new)
        rows = self.con.execute(sqlite_dialect(copy_sql)).fetchall()
        cols = [d[0] for d in self.con.execute("SELECT * FROM PurchaseRequests LIMIT 1").description]
        self.con.execute("UPDATE etl_Watermark SET WatermarkValue = ? WHERE TableName = 'dbo.PurchaseRequests'", (new,))
        return pd.DataFrame(rows, columns=cols)


def test_activity_order_and_dependencies():
    names = [a["name"] for a in PIPELINE["activities"]]
    assert names == ["LookupOldWatermark", "LookupNewWatermark", "CopyDeltaToBronze", "WriteWatermark"]
    assert {d["activity"] for d in ACT["CopyDeltaToBronze"]["dependsOn"]} == {"LookupOldWatermark", "LookupNewWatermark"}
    assert ACT["WriteWatermark"]["dependsOn"][0]["activity"] == "CopyDeltaToBronze"
    assert ACT["WriteWatermark"]["dependsOn"][0]["dependencyConditions"] == ["Succeeded"], \
        "the watermark may only move after a successful copy"


def test_window_is_open_below_closed_above():
    q = ACT["CopyDeltaToBronze"]["typeProperties"]["source"]["sqlReaderQuery"]
    assert "ModifiedOn > '@{activity('LookupOldWatermark')" in q
    assert "ModifiedOn <= '@{activity('LookupNewWatermark')" in q


def test_first_run_copies_everything_then_second_run_copies_only_the_changes(history):
    src = Source()
    src.load(syn.snapshot(history, syn.T1))
    run1 = src.run_pipeline()
    assert len(run1) == len(syn.delta(history, None, syn.T1))
    assert src.one("SELECT WatermarkValue FROM etl_Watermark")[0] == run1["ModifiedOn"].max()

    src.load(syn.snapshot(history, syn.T2))          # the operational system keeps working
    run2 = src.run_pipeline()
    expected = syn.delta(history, syn.T1, syn.T2)
    assert sorted(run2["RequestId"]) == sorted(expected["RequestId"])
    assert (run2["ModifiedOn"] > run1["ModifiedOn"].max()).all()


def test_rerun_without_changes_copies_nothing_and_keeps_the_watermark(history):
    src = Source()
    src.load(syn.snapshot(history, syn.T1))
    src.run_pipeline()
    before = src.one("SELECT WatermarkValue FROM etl_Watermark")[0]
    again = src.run_pipeline()
    assert len(again) == 0
    assert src.one("SELECT WatermarkValue FROM etl_Watermark")[0] == before


def test_empty_source_does_not_break_the_second_lookup():
    src = Source()
    again = src.run_pipeline()
    assert len(again) == 0
    assert src.one("SELECT WatermarkValue FROM etl_Watermark")[0] == "1900-01-01T00:00:00"


def test_a_row_that_arrives_after_the_lookup_is_picked_up_by_the_next_run(history):
    """Why the upper bound is the looked-up maximum and not 'now'."""
    src = Source()
    snap = syn.snapshot(history, syn.T1)
    src.load(snap)
    old = "1900-01-01T00:00:00"
    new = src.one(render(ACT["LookupNewWatermark"]["typeProperties"]["source"]["sqlReaderQuery"]))[0]
    late = snap.iloc[[0]].copy()
    late["RequestId"] = 8888
    late["ModifiedOn"] = pd.Timestamp(new) + pd.Timedelta(minutes=5)   # committed between the lookup and the copy
    src.load(late)
    copy_sql = render(ACT["CopyDeltaToBronze"]["typeProperties"]["source"]["sqlReaderQuery"], old, new)
    got = {r[0] for r in src.con.execute(sqlite_dialect(copy_sql)).fetchall()}
    assert 8888 not in got
    src.con.execute("UPDATE etl_Watermark SET WatermarkValue = ?", (new,))
    assert 8888 in set(src.run_pipeline()["RequestId"])


def test_sink_is_parquet_in_a_dated_folder_with_the_run_id_in_the_file_name():
    out = ACT["CopyDeltaToBronze"]["outputs"][0]
    assert ACT["CopyDeltaToBronze"]["typeProperties"]["sink"]["type"] == "ParquetSink"
    assert "ingest_date=" in out["parameters"]["FolderPath"]
    assert "pipeline().RunId" in out["parameters"]["FileName"], "run id in the name: a retried run cannot overwrite another run's file"


def test_datasets_referenced_by_the_pipeline_exist():
    assert json.loads((ADF / "dataset-source-sql.json").read_text())["type"] == "AzureSqlTable"
    bronze = json.loads((ADF / "dataset-bronze-parquet.json").read_text())
    assert bronze["type"] == "Parquet" and bronze["typeProperties"]["location"]["fileSystem"] == "lake"
    assert set(bronze["parameters"]) == set(ACT["CopyDeltaToBronze"]["outputs"][0]["parameters"])


def test_bronze_path_the_pipeline_writes_matches_the_path_the_view_reads():
    bronze_sql = (pathlib.Path(__file__).resolve().parents[1] / "sql" / "synapse" / "020-bronze.sql").read_text()
    folder = ACT["CopyDeltaToBronze"]["outputs"][0]["parameters"]["FolderPath"]
    prefix = re.search(r"'(bronze/[a-z_]+)/", folder).group(1)
    assert f"BULK '{prefix}/*/*.parquet'" in bronze_sql
