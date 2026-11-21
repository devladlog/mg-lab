# Databricks notebook source
# Needs a workspace. Runs the same functions the local tests run. Paths are abfss URIs of the lake container;
# Unity Catalog governs access through an external location, so no keys appear here.
# COMMAND ----------
dbutils.widgets.text("lake_root", "abfss://lake@<storage-account>.dfs.core.windows.net")
dbutils.widgets.text("source", "abfss://lake@<storage-account>.dfs.core.windows.net/landing/orders")
dbutils.widgets.text("batch_id", "")

# COMMAND ----------
from lakehouse.medallion import run_batch  # package installed on the cluster (wheel or workspace files)

batch_id = dbutils.widgets.get("batch_id")
assert batch_id, "pass a batch_id, for example 2026-03-16T0100"
print(run_batch(spark, dbutils.widgets.get("source"), dbutils.widgets.get("lake_root"), batch_id))
