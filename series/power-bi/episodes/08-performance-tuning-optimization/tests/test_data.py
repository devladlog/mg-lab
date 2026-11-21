"""The generated export, and what the data reduction does to it (measured on the real CSV)."""
import csv
import hashlib
import json
import re
from decimal import Decimal

import gen_sales
import reduce_demo
from conftest import SRC

EXPECTED = json.loads((SRC / "expected" / "reduction-200k.json").read_text(encoding="utf-8"))


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_generator_is_deterministic(tmp_path):
    a = gen_sales.generate(tmp_path / "a", 3000)
    b = gen_sales.generate(tmp_path / "b", 3000)
    assert md5(a) == md5(b)
    c = gen_sales.generate(tmp_path / "c", 3000, seed=7)
    assert md5(a) != md5(c)


def test_export_shape(data20k):
    header, rows = reduce_demo.read(data20k / "sales_detail.csv")
    assert header == gen_sales.SALES_HEADER
    assert len(rows) == 20_000
    assert all(re.fullmatch(r"SO-\d{7}", r["OrderNumber"]) for r in rows)
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", r["OrderTimestamp"]) for r in rows)
    keys = {int(r["CustomerKey"]) for r in rows}
    assert max(keys) <= 5000 and min(keys) >= 1
    # every order date and ship date exists in the date dimension
    with open(data20k / "date.csv", newline="") as f:
        dates = {r["Date"] for r in csv.DictReader(f)}
    assert {r["OrderTimestamp"][:10] for r in rows} <= dates and {r["ShipDate"] for r in rows} <= dates


def test_keys_exist_in_the_dimensions(data20k):
    def keys(name, col):
        with open(data20k / name, newline="") as f:
            return {r[col] for r in csv.DictReader(f)}
    _, rows = reduce_demo.read(data20k / "sales_detail.csv")
    assert {r["ProductKey"] for r in rows} <= keys("product.csv", "ProductKey")
    assert {r["StoreKey"] for r in rows} <= keys("store.csv", "StoreKey")
    assert {r["CustomerKey"] for r in rows} <= keys("customer.csv", "CustomerKey")


def test_reduction_matches_the_committed_numbers(data200k):
    got = reduce_demo.run(data200k)
    assert json.loads(json.dumps(got)) == EXPECTED


def test_reduction_changes_the_model_but_not_the_answers(data200k):
    r = EXPECTED
    assert r["before"]["totals"] == r["after"]["totals"]
    assert r["after"]["rows"] == r["before"]["rows"]
    assert len(r["after"]["columns"]) < len(r["before"]["columns"])
    assert r["after"]["sum_of_column_bits"] < r["before"]["sum_of_column_bits"]
    assert r["before"]["columns"]["LineRef"]["uniqueness"] == 1.0
    assert r["after"]["columns"]["OrderDate"]["distinct"] < r["before"]["columns"]["OrderTimestamp"]["distinct"] / 10


def test_every_group_total_is_the_same_before_and_after(data20k):
    """Not just the grand total: the sales amount of every month and store is identical in both pipelines."""
    header, rows = reduce_demo.read(data20k / "sales_detail.csv")
    cols, reduced = reduce_demo.reduce_rows(header, rows)

    def group(rs, date, amount):
        out = {}
        for r in rs:
            k = (date(r)[:7], r["StoreKey"])
            out[k] = out.get(k, Decimal(0)) + Decimal(amount(r))
        return out
    before = group(rows, lambda r: r["OrderTimestamp"], lambda r: Decimal(r["Quantity"]) * Decimal(r["UnitPrice"]))
    after = group(reduced, lambda r: r["OrderDate"], lambda r: r["LineAmount"])
    assert before == after and len(before) > 100


def test_order_number_is_a_whole_number_after_the_reduction(data20k):
    header, rows = reduce_demo.read(data20k / "sales_detail.csv")
    _, reduced = reduce_demo.reduce_rows(header, rows)
    assert all(r["OrderNumber"].isdigit() for r in reduced)
    assert len({r["OrderNumber"] for r in reduced}) == len({r["OrderNumber"] for r in rows})


def test_profile_flags_prefixed_numbers(data20k):
    header, rows = reduce_demo.read(data20k / "sales_detail.csv")
    p = reduce_demo.profile(header, rows)
    assert p["OrderNumber"]["prefixed_number"] and not p["LineRef"]["prefixed_number"] and not p["CustomerKey"]["prefixed_number"]


def test_expected_totals_agree_with_the_reduction_and_the_committed_file(data200k):
    import expected_totals
    t = expected_totals.totals(data200k)
    assert t == json.loads((SRC / "expected" / "totals-200k.json").read_text(encoding="utf-8"))
    r = EXPECTED["before"]["totals"]
    assert (t["sales_amount"], t["units"], t["orders"]) == (r["sales_amount"], r["units"], r["orders"])
    assert t["margin_percent"] == "40.0"


def test_the_demo_size_totals_are_committed():
    """Made once with gen_sales.py --rows 2000000 (about 25 seconds, 177 MB): too big to regenerate in every test run."""
    t = json.loads((SRC / "expected" / "totals-2m.json").read_text(encoding="utf-8"))
    assert t["lines"] == 2_000_000 and t["orders"] > 790_000 and Decimal(t["sales_amount"]) > Decimal("2.8e9")
