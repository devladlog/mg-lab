"""A small local Spark session with open-source Delta Lake (tests and the local demo)."""
from __future__ import annotations

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession


def local_spark(app: str = "contoso-lakehouse-local", memory: str = "1g") -> SparkSession:
    builder = (SparkSession.builder.master("local[2]").appName(app)
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.sql.shuffle.partitions", "2")
               .config("spark.default.parallelism", "2")
               .config("spark.ui.enabled", "false")
               .config("spark.driver.memory", memory)
               .config("spark.sql.session.timeZone", "UTC"))
    return configure_spark_with_delta_pip(builder).getOrCreate()
