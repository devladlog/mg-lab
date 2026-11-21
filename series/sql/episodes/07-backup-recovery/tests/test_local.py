"""The local half: the lab's data statements executed on DuckDB (orders, the accident, the repair), with the
restore modelled as a copy of the tables taken at the mark; and expected/ checked against an independent
reading of the seed data."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import backup_lab as lab  # noqa: E402
import labdb  # noqa: E402

SEED = lab.sql_text("01-schema-and-data.sql")
PRODUCTS = re.findall(r"^\s+\((\d), N'([^']+)',\s+([\d.]+),\s+(\d+)\)", SEED, re.MULTILINE)
SEED_ORDERS = re.findall(r"^\s+\((10\d\d), \d, '[\d-]+', N'\w+'\)", SEED, re.MULTILINE)


def expected(key):
    return labdb.read_csv(ROOT / "expected" / f"{key}.csv")


def test_seed_has_five_products_and_eight_orders():
    assert len(PRODUCTS) == 5 and len(SEED_ORDERS) == 8


def test_local_run_matches_expected(capsys):
    assert lab.run_local() == 0
    assert "the data model matches expected/" in capsys.readouterr().out


def test_expected_counts_follow_from_the_seed_and_the_data_files():
    new_orders = {"d01": 2, "d02": 1, "b05": 1}                   # orders inserted by d01, d02 and after the accident
    for key, n in new_orders.items():
        text = lab.sql_text({"d01": "d01-orders-after-full", "d02": "d02-order-after-diff", "b05": "b05-incident"}[key])
        assert len(re.findall(r"^\s+\((10\d\d), \d, '", text, re.MULTILINE)) == n, key
    all_orders = len(SEED_ORDERS) + sum(new_orders.values())
    live_after_incident = {r[0]: r[1] for r in expected("b05-incident")[1:]}
    assert live_after_incident == {"Products priced at 0": str(len(PRODUCTS)), "Orders in the live database": str(all_orders)}
    copy = {r[0]: r[1] for r in expected("b06-restore-copy")[1:]}
    assert copy["Orders in the copy"] == str(all_orders - 1)      # everything except the order after the accident
    assert copy["Order 1012 in the copy"] == "0" and copy["Products priced at 0 in the copy"] == "0"
    repaired = {r[0]: r[1] for r in expected("b07-verify-and-repair")[1:]}
    assert repaired["Orders in the live database"] == str(all_orders)   # the repair keeps order 1012
    assert repaired["Prices equal to the copy"] == str(len(PRODUCTS))


def test_backup_kinds_in_expected_files():
    assert [expected(k)[1][0] for k in ("b02-full-backup", "b03-differential-backup", "b04-log-backup")] == \
        ["Full", "Differential", "Log"]
    for k in ("b02-full-backup", "b03-differential-backup", "b04-log-backup"):
        assert expected(k)[1][1:] == ["FULL", "1", "0"]            # FULL recovery, checksums, not copy-only
