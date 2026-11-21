"""Run the whole medallion locally on generated fictional data:  python -m lakehouse.run_local ./lake-demo"""
from __future__ import annotations

import shutil
import sys

from . import datagen
from .contract import GOLD_TABLES
from .medallion import run_batch, table_path
from .session import local_spark


def main(root: str, batches: int = 3) -> None:
    shutil.rmtree(root, ignore_errors=True)
    spark = local_spark()
    spark.sparkContext.setLogLevel("ERROR")
    for n in range(1, batches + 1):
        src = f"{root}/landing/batch{n}"
        datagen.make_batch(src, n)
        print(f"batch {n}:", run_batch(spark, src, root, f"b{n}"))
    for name in GOLD_TABLES:
        print(f"\ngold.{name}")
        spark.read.format("delta").load(table_path(root, f"gold_{name}")).orderBy(*list(GOLD_TABLES[name])[:2]).show(5, False)
    print("quarantine by reason")
    spark.read.format("delta").load(table_path(root, "quarantine")).groupBy("reject_reason").count().show()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "./lake-demo")
