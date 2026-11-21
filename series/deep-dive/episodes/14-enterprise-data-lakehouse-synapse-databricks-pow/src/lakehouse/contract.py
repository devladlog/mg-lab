"""Single source of truth for the Contoso orders lakehouse.

Silver and gold column lists live here. The Synapse views, the Power BI model and the
tests all check themselves against this file, so a renamed column fails a test, not a report.
"""
from pyspark.sql import types as T

CURRENCIES = ("USD", "EUR", "GBP")
OPS = ("I", "U", "D")  # insert, update, delete: the change feed from the order system

# Delta tables written with deletion vectors off: Synapse serverless reads Delta reader v1
# and ignores deletion vectors (Microsoft Learn, serverless SQL pool self-help).
TABLE_PROPERTIES = {"delta.enableDeletionVectors": "false"}

BRONZE_SCHEMA = T.StructType([
    T.StructField("order_id", T.StringType()),
    T.StructField("op", T.StringType()),
    T.StructField("seq", T.LongType()),
    T.StructField("customer_email", T.StringType()),
    T.StructField("region", T.StringType()),
    T.StructField("currency", T.StringType()),
    T.StructField("amount", T.DecimalType(12, 2)),
    T.StructField("order_ts", T.StringType()),
    T.StructField("_corrupt_record", T.StringType()),
])

# name -> Spark SQL type string, in column order
SILVER_COLUMNS = {
    "order_id": "string",
    "seq": "bigint",
    "customer_key": "string",
    "region": "string",
    "currency": "string",
    "amount": "decimal(12,2)",
    "order_ts": "timestamp",
    "order_date": "date",
    "source_file": "string",
    "batch_id": "string",
}

GOLD_TABLES = {
    "daily_sales": {
        "order_date": "date",
        "region": "string",
        "currency": "string",
        "orders": "bigint",
        "revenue": "decimal(22,2)",
    },
    "customer_summary": {
        "customer_key": "string",
        "orders": "bigint",
        "revenue": "decimal(22,2)",
        "first_order_date": "date",
        "last_order_date": "date",
    },
}

LAYOUT = {
    "bronze": "bronze/orders",
    "silver": "silver/orders",
    "quarantine": "silver/orders_quarantine",
    "gold_daily_sales": "gold/daily_sales",
    "gold_customer_summary": "gold/customer_summary",
}
