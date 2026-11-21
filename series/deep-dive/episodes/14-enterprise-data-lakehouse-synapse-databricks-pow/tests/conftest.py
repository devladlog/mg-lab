import json
from pathlib import Path

import pytest

from lakehouse.session import local_spark


@pytest.fixture(scope="session")
def spark():
    s = local_spark("contoso-lakehouse-tests")
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


def write_rows(folder: Path, name: str, rows, raw_lines=()):
    folder.mkdir(parents=True, exist_ok=True)
    text = "\n".join([json.dumps(r) for r in rows] + list(raw_lines)) + "\n"
    (folder / name).write_text(text, encoding="utf-8")
    return str(folder)


def order(oid, op="I", seq=1, email="alex.demo@contoso.example", region="emea", cur="EUR",
          amount=10.0, ts="2026-02-03T10:00:00"):
    return {"order_id": oid, "op": op, "seq": seq, "customer_email": email, "region": region,
            "currency": cur, "amount": amount, "order_ts": ts}


def delta_state(spark, path):
    """What a Delta reader v1 sees (Synapse serverless): active parquet files from add/remove actions,
    read as plain parquet. Deletion vectors are ignored, exactly like the documented limitation."""
    adds, dvs = {}, 0
    for f in sorted((Path(path) / "_delta_log").glob("*.json")):
        actions = [json.loads(line) for line in f.read_text().splitlines()]
        for a in actions:                       # within one commit, removes apply before adds
            if "remove" in a:
                adds.pop(a["remove"]["path"], None)
        for a in actions:
            if "add" in a:
                adds[a["add"]["path"]] = a["add"]
                dvs += 1 if a["add"].get("deletionVector") else 0
    files = [f"{path}/{p}" for p in adds]
    return spark.read.parquet(*files) if files else None, dvs
