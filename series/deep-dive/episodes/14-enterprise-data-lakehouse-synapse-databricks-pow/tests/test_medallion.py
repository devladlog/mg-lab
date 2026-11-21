import json
from pathlib import Path

from pyspark.sql import functions as F

from conftest import delta_state, order, write_rows
from lakehouse import medallion as m
from lakehouse.contract import GOLD_TABLES, SILVER_COLUMNS


def read(spark, root, name):
    return spark.read.format("delta").load(m.table_path(str(root), name))


def run(spark, tmp_path, rows, batch, raw=()):
    src = write_rows(tmp_path / "landing" / batch, f"{batch}.jsonl", rows, raw)
    return m.run_batch(spark, src, str(tmp_path / "lake"), batch)


def test_bronze_keeps_everything_and_records_file(spark, tmp_path):
    stats = run(spark, tmp_path, [order("A1"), order("A2")], "b1", raw=['{"order_id": "broken'])
    bronze = read(spark, tmp_path / "lake", "bronze")
    assert stats["ingested"] == 3
    assert bronze.filter("_corrupt_record IS NOT NULL").count() == 1
    assert {r.source_file for r in bronze.collect()} == {"b1.jsonl"}


def test_quality_rules_name_each_reason(spark, tmp_path):
    rows = [order("ok"), order("", seq=2), order("x", op="Z"), order("c", cur="XXX"),
            order("neg", amount=-1), order("ts", ts="not a time"), order("gone", op="D", cur=None, amount=None, ts=None)]
    run(spark, tmp_path, rows, "b1", raw=['{"order_id": "broken'])
    q = {r.reject_reason: r['count'] for r in read(spark, tmp_path / "lake", "quarantine").groupBy("reject_reason").count().collect()}
    assert q == {"unparseable_record": 1, "missing_order_id": 1, "bad_op": 1, "bad_currency": 1,
                 "bad_amount": 1, "bad_timestamp": 1}
    silver = {r.order_id for r in read(spark, tmp_path / "lake", "silver").collect()}
    assert silver == {"ok"}            # the delete of an unknown order is valid but changes nothing


def test_merge_insert_update_delete_and_dedupe(spark, tmp_path):
    run(spark, tmp_path, [order("A", amount=10), order("B", amount=20), order("C", amount=30)], "b1")
    run(spark, tmp_path, [order("A", op="U", seq=5, amount=11), order("A", op="U", seq=7, amount=12),
                          order("B", op="D", seq=6), order("D", seq=8, amount=40)], "b2")
    got = {r.order_id: float(r.amount) for r in read(spark, tmp_path / "lake", "silver").collect()}
    assert got == {"A": 12.0, "C": 30.0, "D": 40.0}   # two updates in one batch: highest seq wins


def test_late_and_replayed_rows_lose(spark, tmp_path):
    run(spark, tmp_path, [order("A", seq=10, amount=10)], "b1")
    run(spark, tmp_path, [order("A", op="U", seq=3, amount=99)], "b2")        # older than what silver has
    run(spark, tmp_path, [order("A", op="D", seq=2)], "b3")                   # stale delete
    assert [float(r.amount) for r in read(spark, tmp_path / "lake", "silver").collect()] == [10.0]
    root = str(tmp_path / "lake")
    before = read(spark, tmp_path / "lake", "silver").count()
    m.silver_merge(spark, root, "b1")                                          # replay a whole batch
    assert read(spark, tmp_path / "lake", "silver").count() == before


def test_no_email_outside_bronze(spark, tmp_path):
    run(spark, tmp_path, [order("A", email=" Alex.Demo@Contoso.example ")], "b1")
    silver = read(spark, tmp_path / "lake", "silver")
    assert "customer_email" not in silver.columns
    key = silver.collect()[0].customer_key
    assert len(key) == 64 and "contoso" not in key
    assert key == spark.range(1).select(F.sha2(F.lit("alex.demo@contoso.example"), 256)).collect()[0][0]
    for name in GOLD_TABLES:
        assert "customer_email" not in read(spark, tmp_path / "lake", f"gold_{name}").columns


def test_gold_numbers(spark, tmp_path):
    run(spark, tmp_path, [order("A", amount=10.5), order("B", amount=20.25),
                          order("C", region="amer", cur="USD", amount=5, ts="2026-02-04T09:00:00")], "b1")
    root = tmp_path / "lake"
    d = {(str(r.order_date), r.region): (r.orders, str(r.revenue)) for r in read(spark, root, "gold_daily_sales").collect()}
    assert d == {("2026-02-03", "emea"): (2, "30.75"), ("2026-02-04", "amer"): (1, "5.00")}
    cs = read(spark, root, "gold_customer_summary").collect()
    assert len(cs) == 1 and cs[0].orders == 3 and str(cs[0].last_order_date) == "2026-02-04"


def test_on_disk_schema_matches_contract(spark, tmp_path):
    run(spark, tmp_path, [order("A")], "b1")
    root = tmp_path / "lake"
    silver = {f.name: f.dataType.simpleString() for f in read(spark, root, "silver").schema}
    assert silver == SILVER_COLUMNS
    for name, cols in GOLD_TABLES.items():
        got = {f.name: f.dataType.simpleString() for f in read(spark, root, f"gold_{name}").schema}
        assert got == cols


def test_synapse_reader_v1_sees_same_rows_when_deletion_vectors_off(spark, tmp_path):
    run(spark, tmp_path, [order("A"), order("B"), order("C")], "b1")
    run(spark, tmp_path, [order("B", op="D", seq=9), order("C", op="U", seq=9, amount=77)], "b2")
    silver_path = m.table_path(str(tmp_path / "lake"), "silver")
    v1, dvs = delta_state(spark, silver_path)
    assert dvs == 0
    assert sorted((r.order_id, float(r.amount)) for r in v1.collect()) == [("A", 10.0), ("C", 77.0)]


def test_deletion_vectors_make_reader_v1_return_deleted_rows(spark, tmp_path):
    """The failure mode, reproduced: DVs on -> a v1 reader (Synapse serverless) still returns the deleted row."""
    path = str(tmp_path / "dv")
    (spark.range(0, 100).selectExpr("id", "cast(id as string) as name").repartition(1)
     .write.format("delta").option("delta.enableDeletionVectors", "true").save(path))
    spark.sql(f"ALTER TABLE delta.`{path}` SET TBLPROPERTIES ('delta.enableDeletionVectors' = 'true')")
    spark.sql(f"DELETE FROM delta.`{path}` WHERE id = 7")
    delta_count = spark.read.format("delta").load(path).filter("id = 7").count()
    v1, dvs = delta_state(spark, path)
    assert delta_count == 0 and dvs >= 1
    assert v1.filter("id = 7").count() == 1
