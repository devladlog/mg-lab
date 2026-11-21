"""Bronze -> silver -> gold for the Contoso orders change feed (PySpark + Delta Lake).

Plain functions over a SparkSession, so the same code runs in a Databricks notebook and in the
local pytest run (open-source Delta Lake). Nothing here is Databricks-only.
"""
from __future__ import annotations

from delta.tables import DeltaTable
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from .contract import (BRONZE_SCHEMA, CURRENCIES, GOLD_TABLES, LAYOUT, OPS,
                       SILVER_COLUMNS, TABLE_PROPERTIES)


def table_path(root: str, name: str) -> str:
    return f"{root.rstrip('/')}/{LAYOUT[name]}"


def _create_if_missing(spark: SparkSession, path: str, columns: dict) -> None:
    builder = DeltaTable.createIfNotExists(spark).location(path)
    for name, dtype in columns.items():
        builder = builder.addColumn(name, dtype)
    for key, value in TABLE_PROPERTIES.items():
        builder = builder.property(key, value)
    builder.execute()


# ---------------------------------------------------------------- bronze
def bronze_ingest(spark: SparkSession, source: str, root: str, batch_id: str) -> int:
    """Append raw JSON lines as-is. Keeps bad rows (in _corrupt_record) so nothing is lost."""
    raw = (spark.read.schema(BRONZE_SCHEMA)
           .option("mode", "PERMISSIVE")
           .option("columnNameOfCorruptRecord", "_corrupt_record")
           .json(source)
           .select("*", F.col("_metadata.file_name").alias("source_file")))  # not input_file_name()
    out = (raw.withColumn("batch_id", F.lit(batch_id))
              .withColumn("ingested_at", F.current_timestamp()))
    out.write.format("delta").mode("append").save(table_path(root, "bronze"))
    return out.count()


# ---------------------------------------------------------------- silver
def split_quality(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Return (valid, rejected). The first failing rule names the reason; deletes need only a key."""
    live = F.col("op") != "D"
    parsed_ts = F.try_to_timestamp("order_ts")
    reason = (F.when(F.col("_corrupt_record").isNotNull(), "unparseable_record")
              .when(F.col("order_id").isNull() | (F.trim("order_id") == ""), "missing_order_id")
              .when(~F.col("op").isin(*OPS) | F.col("op").isNull(), "bad_op")
              .when(F.col("seq").isNull(), "missing_seq")
              .when(live & ~F.col("currency").isin(*CURRENCIES), "bad_currency")
              .when(live & (F.col("amount").isNull() | (F.col("amount") < 0)), "bad_amount")
              .when(live & parsed_ts.isNull(), "bad_timestamp"))
    tagged = df.withColumn("reject_reason", reason)
    return tagged.filter("reject_reason IS NULL").drop("reject_reason"), tagged.filter("reject_reason IS NOT NULL")


def _to_silver_shape(df: DataFrame) -> DataFrame:
    email = F.lower(F.trim("customer_email"))
    return (df.select(
        "order_id", "seq", "op",
        F.when(email.isNotNull(), F.sha2(email, 256)).alias("customer_key"),  # PII stays in bronze
        "region", "currency", "amount",
        F.try_to_timestamp("order_ts").alias("order_ts"),
        F.to_date(F.try_to_timestamp("order_ts")).alias("order_date"),
        "source_file", "batch_id"))


def silver_merge(spark: SparkSession, root: str, batch_id: str) -> dict:
    """Apply one bronze batch to silver: dedupe, quarantine, then MERGE (insert/update/delete)."""
    batch = spark.read.format("delta").load(table_path(root, "bronze")).filter(F.col("batch_id") == batch_id)
    valid, rejected = split_quality(batch)

    quarantine = rejected.select("order_id", "op", "seq", "reject_reason", "_corrupt_record",
                                 "source_file", "batch_id")
    quarantine.write.format("delta").mode("append").save(table_path(root, "quarantine"))

    newest = Window.partitionBy("order_id").orderBy(F.col("seq").desc())
    latest = (valid.withColumn("_rn", F.row_number().over(newest)).filter("_rn = 1").drop("_rn"))
    changes = _to_silver_shape(latest)

    path = table_path(root, "silver")
    _create_if_missing(spark, path, SILVER_COLUMNS)
    cols = list(SILVER_COLUMNS)
    (DeltaTable.forPath(spark, path).alias("t")
        .merge(changes.alias("s"), "t.order_id = s.order_id")
        .whenMatchedDelete(condition="s.op = 'D' AND s.seq > t.seq")
        .whenMatchedUpdate(condition="s.op <> 'D' AND s.seq > t.seq",   # replayed or late rows lose
                           set={c: f"s.{c}" for c in cols})
        .whenNotMatchedInsert(condition="s.op <> 'D'", values={c: f"s.{c}" for c in cols})
        .execute())
    return {"batch": batch.count(), "rejected": rejected.count(), "applied": changes.count()}


# ---------------------------------------------------------------- gold
def build_gold(spark: SparkSession, root: str) -> None:
    silver = spark.read.format("delta").load(table_path(root, "silver"))
    daily = (silver.groupBy("order_date", "region", "currency")
             .agg(F.count("*").alias("orders"), F.sum("amount").alias("revenue")))
    customers = (silver.filter(F.col("customer_key").isNotNull()).groupBy("customer_key")
                 .agg(F.count("*").alias("orders"), F.sum("amount").alias("revenue"),
                      F.min("order_date").alias("first_order_date"),
                      F.max("order_date").alias("last_order_date")))
    for name, df in (("daily_sales", daily), ("customer_summary", customers)):
        cols = list(GOLD_TABLES[name])
        (df.select(*[F.col(c).cast(GOLD_TABLES[name][c]) for c in cols])
           .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
           .option("delta.enableDeletionVectors", "false")
           .save(table_path(root, f"gold_{name}")))


def run_batch(spark: SparkSession, source: str, root: str, batch_id: str) -> dict:
    ingested = bronze_ingest(spark, source, root, batch_id)
    stats = silver_merge(spark, root, batch_id)
    build_gold(spark, root)
    return {"ingested": ingested, **stats}
