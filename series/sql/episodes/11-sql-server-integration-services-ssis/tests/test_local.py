"""The local half: the data flow modelled from the .dtsx and the merge statements of the procedure, run on DuckDB."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import etl_lab as lab  # noqa: E402
import labdb  # noqa: E402


def test_local_run_matches_expected(capsys):
    assert lab.run_local() == 0
    assert "match expected/" in capsys.readouterr().out


def test_package_model_is_read_from_the_dtsx():
    m = lab.package_model()
    assert [n for n, _ in m["columns"]] == ["DealerCode", "PartnerOrderRef", "LineNumber", "SaleDate", "ProductId", "Quantity", "UnitPrice"]
    assert m["rule"] == "Quantity > 0 && UnitPrice >= 0"


def test_data_flow_split_of_the_sample_files():
    m = lab.package_model()
    rows = lab.read_flat_file(ROOT / "data" / lab.FILE1, m)
    valid, rejected = lab.split_rows(rows, m["rule"])
    assert (len(rows), len(valid), len(rejected)) == (8, 6, 2)
    assert {(r["PartnerOrderRef"], r["LineNumber"]) for r in rejected} == {("PO-88010", 2), ("PO-88011", 1)}
    rows2 = lab.read_flat_file(ROOT / "data" / lab.FILE2, m)
    assert lab.split_rows(rows2, m["rule"]) == (rows2, [])


def test_wrong_header_is_refused(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Dealer,Ref\nX,1\n", encoding="utf-8")
    try:
        lab.read_flat_file(bad, lab.package_model())
    except ValueError as e:
        assert "does not match the package columns" in str(e)
    else:
        raise AssertionError("expected a ValueError")


def test_rule_evaluator_refuses_anything_but_comparisons():
    try:
        lab.evaluate_rule("__import__('os').system('x') > 0", {"a": 1})
    except ValueError:
        return
    raise AssertionError("expected a ValueError")


def test_merge_statements_are_the_four_steps_in_order():
    assert list(lab.merge_statements()) == ["stamp-flow-rejects", "reject-unknown-products", "update-changed-lines", "insert-new-lines"]


def test_same_file_twice_changes_nothing_and_a_correction_updates_one_line():
    eng = lab.local_setup()
    m = lab.package_model()
    try:
        lab.local_run(eng, m, lab.FILE1)
        before = eng.query("SELECT * FROM Sales.PartnerSales ORDER BY PartnerOrderRef, LineNumber")[1]
        lab.local_run(eng, m, lab.FILE1)
        assert eng.query("SELECT * FROM Sales.PartnerSales ORDER BY PartnerOrderRef, LineNumber")[1] == [
            tuple(r[:-1]) + (r[-1],) for r in before]          # identical, including LoadedRunLogId (nothing was touched)
        lab.local_run(eng, m, lab.FILE2)
        cols, rows = eng.query("SELECT Qty, LoadedRunLogId FROM Sales.PartnerSales WHERE PartnerOrderRef = 'PO-77001' AND LineNumber = 1")
        assert rows == [(3, 3)]                                # quantity 2 -> 3, stamped with the run that corrected it
    finally:
        eng.close()


def test_expected_files_are_consistent_with_the_sample_data():
    exp = {r.key: {row[0]: row[1] for row in labdb.read_csv(ROOT / "expected" / f"{r.key}.csv")[1:]} for r in lab.RUNS}
    assert [e["Execution status"] for e in exp.values()] == ["Succeeded"] * 3
    assert exp["c03-run1-basic"]["Rows sent by Flat File Source (data statistics)"] == "0"      # Basic logging: no row counts
    assert exp["c03-run2-rerun-verbose"]["Rows sent by Flat File Source (data statistics)"] == "8"   # Verbose: all 8 rows of the file
    assert exp["c03-run3-correction"]["Rows sent by Flat File Source (data statistics)"] == "3"
    assert int(exp["c03-run3-correction"]["Lines in Sales.PartnerSales"]) == 5 + 2
