"""The two semantic models and perf-lint: the before model has every problem, the after model has none."""
import json
import re
import shutil
import subprocess
import sys
from collections import Counter

import pytest

import build_models
import extract_m
import perf_lint as pl
import reduce_demo
from conftest import AFTER, AFTER_REPORT, BEFORE, BEFORE_REPORT, SRC

TMDL_LOAD = SRC / "TmdlLoad" / "bin" / "Debug" / "net8.0" / "tmdl-load.dll"
PQ_LINT = SRC / "pq-lint" / "dist" / "src" / "cli.js"
needs_tom = pytest.mark.skipif(not TMDL_LOAD.exists(), reason="build tmdl-load first: dotnet build src/TmdlLoad -m:1")
needs_pq_lint = pytest.mark.skipif(not PQ_LINT.exists(), reason="build pq-lint first: cd src/pq-lint && npm ci && npm test")
PROFILE = json.loads((SRC / "expected" / "reduction-200k.json").read_text(encoding="utf-8"))


def rules(findings):
    return Counter((f["rule"], f["severity"]) for f in findings)


def test_models_match_their_description():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_models.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_before_model_has_each_problem_once():
    f = pl.lint(BEFORE, [BEFORE_REPORT], PROFILE["before"]["columns"])
    got = rules(f)
    assert got == Counter({("PF001", "warning"): 1, ("PF002", "warning"): 1, ("PF003", "warning"): 1,
                           ("PF004", "warning"): 1, ("PF005", "warning"): 1, ("PF006", "warning"): 1,
                           ("PF007", "warning"): 1, ("PF008", "warning"): 1, ("PF009", "warning"): 1,
                           ("PF010", "warning"): 1, ("PF011", "warning"): 2}), f
    where = {x["rule"]: x["where"] for x in f}
    assert where["PF001"] == "LocalDateTable_OrderDate"
    assert where["PF002"] == "Sales to Product"
    assert where["PF007"] == "Sales[Online Sales]" and where["PF008"] == "Sales[Margin %]" and where["PF009"] == "Sales[Sales YoY %]"
    assert {x["where"] for x in f if x["rule"] == "PF011"} == {"Sales[Line Ref]", "Sales[Note]"}


def test_after_model_is_clean_even_with_the_strictest_options():
    assert pl.lint(AFTER, [AFTER_REPORT], PROFILE["after"]["columns"]) == []


def test_cli_exit_codes():
    run = lambda *a: subprocess.run([sys.executable, str(SRC / "tools" / "perf_lint.py"), *a], capture_output=True, text=True)
    assert run("--model", str(BEFORE)).returncode == 0                       # warnings only: advisory
    assert run("--model", str(BEFORE), "--strict").returncode == 1
    assert run("--model", str(AFTER), "--strict").returncode == 0
    assert run("--model", str(SRC)).returncode == 2


def copy_after(tmp_path):
    dst = tmp_path / "definition"
    shutil.copytree(AFTER, dst)
    return dst


def edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize("rule, file, old, new", [
    ("PF002", "relationships.tmdl", "relationship 'Sales to Store'\n", "relationship 'Sales to Store'\n\tcrossFilteringBehavior: bothDirections\n"),
    ("PF003", "tables/Sales.tmdl", "\tcolumn 'Line Amount'\n\t\tdataType: decimal\n", "\tcolumn 'Line Amount' = Sales[Quantity] * 2\n\t\tdataType: decimal\n"),
    ("PF004", "tables/Sales.tmdl", "formatString: yyyy-mm-dd\n\t\tsummarizeBy: none\n\t\tsourceColumn: OrderDate", "formatString: yyyy-mm-dd hh:mm:ss\n\t\tsummarizeBy: none\n\t\tsourceColumn: OrderDate"),
    ("PF007", "tables/Sales.tmdl", "KEEPFILTERS('Store'[Channel] = \"Online\")", "FILTER(Store, 'Store'[Channel] = \"Online\")"),
    ("PF007", "tables/Sales.tmdl", "KEEPFILTERS('Store'[Channel] = \"Online\")", "FILTER('Store', 'Store'[Channel] = \"Online\")"),
    ("PF008", "tables/Sales.tmdl", "DIVIDE([Margin], [Sales Amount])", "IFERROR(DIVIDE([Margin], [Sales Amount]), 0)"),
    ("PF008", "tables/Sales.tmdl", "DIVIDE([Margin], [Sales Amount])", "[Margin] / [Sales Amount]"),
    ("PF009", "tables/Sales.tmdl", "VAR PriorSales = CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date]))\n\t\t\tRETURN\n\t\t\t    DIVIDE([Sales Amount] - PriorSales, PriorSales)",
     "DIVIDE([Sales Amount] - CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date])), CALCULATE([Sales Amount], SAMEPERIODLASTYEAR('Date'[Date])))"),
])
def test_each_rule_fires_when_its_problem_is_added_to_the_after_model(tmp_path, rule, file, old, new):
    d = copy_after(tmp_path)
    edit(d / file, old, new)
    assert rule in {f["rule"] for f in pl.lint(d)}


def test_pf001_pf011_on_the_after_model(tmp_path):
    d = copy_after(tmp_path)
    (d / "tables" / "LocalDateTable_x.tmdl").write_text(
        "table LocalDateTable_x\n\tisHidden\n\n\tpartition LocalDateTable_x = calculated\n\t\tmode: import\n"
        "\t\tsource = CALENDAR(DATE(2023, 1, 1), DATE(2023, 12, 31))\n", encoding="utf-8")
    assert "PF001" in {f["rule"] for f in pl.lint(d)}
    edit(d / "tables" / "Sales.tmdl", "\tpartition Sales = m", "\tcolumn Spare\n\t\tdataType: string\n\t\tisHidden\n\t\tsourceColumn: Spare\n\n\tpartition Sales = m")
    assert [f["where"] for f in pl.lint(d) if f["rule"] == "PF011"] == ["Sales[Spare]"]


def test_pf005_and_pf006_need_the_profile(tmp_path):
    d = copy_after(tmp_path)
    edit(d / "tables" / "Sales.tmdl", "column 'Order Number'\n\t\tdataType: int64", "column 'Order Number'\n\t\tdataType: string")
    assert pl.lint(d) == []                                                   # no profile, no verdict
    prof = {"OrderNumber": {"distinct": 80059, "uniqueness": 0.4, "prefixed_number": True}}
    assert [f["rule"] for f in pl.lint(d, profile=prof)] == ["PF006"]
    prof["OrderNumber"]["uniqueness"] = 0.9
    assert {f["rule"] for f in pl.lint(d, profile=prof)} == {"PF005", "PF006"}


def test_the_right_uses_of_filter_and_slash_are_not_flagged(tmp_path):
    """Learn: FILTER is needed when the condition uses a measure; '/' is fine with a constant denominator."""
    d = copy_after(tmp_path)
    edit(d / "tables" / "Sales.tmdl", "\tmeasure Units = SUM(Sales[Quantity])\n",
         "\tmeasure 'Big Customers' = COUNTROWS(FILTER(VALUES('Customer'[CustomerKey]), [Sales Amount] > 1000))\n"
         "\t\tformatString: #,0\n\n\tmeasure Half = [Sales Amount] / 2\n\t\tformatString: #,0\n\n"
         "\tmeasure 'Good Months' = CALCULATE([Sales Amount], FILTER(VALUES('Date'[Year Month]), [Margin] > 0))\n\t\tformatString: #,0\n\n"
         "\tmeasure Units = SUM(Sales[Quantity])\n")
    assert pl.lint(d) == []


def test_a_security_relationship_is_info_not_a_warning(tmp_path):
    d = copy_after(tmp_path)
    edit(d / "relationships.tmdl", "relationship 'Sales to Customer'\n",
         "relationship 'Sales to Customer'\n\tcrossFilteringBehavior: bothDirections\n\tsecurityFilteringBehavior: bothDirections\n")
    assert rules(pl.lint(d)) == Counter({("PF002", "info"): 1})


def test_dax_text_helpers():
    assert pl.calls('CALCULATE(a, FILTER(T, x = "(,"))', "CALCULATE")[0][2] == ["a", 'FILTER(T, x = "(,")']
    assert pl.mask('x "a(" // (\n)') == 'x "  " ' + " " * 4 + "\n)"
    assert pl.squash("A  b\n C") == "abc"


def test_both_models_have_the_same_tables_and_measures():
    b, a = pl.read_model(BEFORE), pl.read_model(AFTER)
    assert set(b) - set(a) == {"LocalDateTable_OrderDate"} and set(a) <= set(b)
    names = lambda m: {x["name"] for x in m["Sales"]["measures"]}
    assert names(b) == names(a) and len(names(a)) == 9


def test_sales_columns_follow_the_python_mirror_of_the_m():
    """The columns the model reads (sourceColumn) are exactly the columns the mirror produces for each model."""
    import gen_sales
    src = lambda m: {c["source"] for c in m["Sales"]["columns"] if c["source"]}
    header = gen_sales.SALES_HEADER
    cols_after, _ = reduce_demo.reduce_rows(header, [dict.fromkeys(header, "SO-1") | {"OrderTimestamp": "2023-01-01T00:00:00", "Quantity": "1", "UnitPrice": "1.00"}])
    assert src(pl.read_model(AFTER)) == set(cols_after)
    assert src(pl.read_model(BEFORE)) == set(header) | {"OrderDate"}            # Line Amount is a DAX column: no source


def test_every_source_column_is_in_the_csv(data20k):
    import csv
    for model in (BEFORE, AFTER):
        for name, t in pl.read_model(model).items():
            for p in t["partitions"]:
                if p["kind"] != "m":
                    continue
                csv_name = re.search(r'DataFolder & "\\([^"]+)"', p["text"]).group(1)
                header = next(csv.reader(open(data20k / csv_name, newline="", encoding="utf-8")))
                derived = {"OrderDate", "LineAmount"}
                missing = {c["source"] for c in t["columns"] if c["source"]} - set(header) - derived
                assert not missing, (name, missing)


@needs_pq_lint
@pytest.mark.parametrize("model", [BEFORE, AFTER], ids=["before", "after"])
def test_every_partition_parses_with_microsofts_parser(tmp_path, model):
    for name, text in extract_m.extract(model).items():
        (tmp_path / f"{name}.pq").write_text(text, encoding="utf-8")
    r = subprocess.run(["node", str(PQ_LINT), str(tmp_path), "--strict"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "6 queries: 0 error(s), 0 warning(s)" in r.stdout


@needs_pq_lint
def test_pq_lint_still_catches_a_broken_partition(tmp_path):
    (tmp_path / "Bad.pq").write_text('let\n    Source = Csv.Document(File.Contents(Folder & "\\x.csv"))\nin\n    Source\n', encoding="utf-8")
    r = subprocess.run(["node", str(PQ_LINT), str(tmp_path), "--strict"], capture_output=True, text=True)
    assert r.returncode == 1 and "PQ002" in r.stdout


@needs_tom
@pytest.mark.parametrize("model, tables", [(BEFORE, 6), (AFTER, 5)], ids=["before", "after"])
def test_tom_loads_the_model(model, tables):
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(model)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert f"{tables} table(s), 1 parameter(s), 5 relationship(s), 0 role(s): loaded" in r.stdout
    assert ("filter=BothDirections" in r.stdout) == (model == BEFORE)


@needs_tom
def test_tom_rejects_a_broken_model(tmp_path):
    d = copy_after(tmp_path)
    edit(d / "relationships.tmdl", "toColumn: Store.StoreKey", "toColumn: Store.Nope")
    r = subprocess.run(["dotnet", str(TMDL_LOAD), str(d)], capture_output=True, text=True)
    assert r.returncode == 1


def test_brief_output_has_one_short_line_per_finding():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "perf_lint.py"), "--model", str(BEFORE), "--brief"],
                       capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    assert lines[-1].endswith("warning(s), 0 info") and all(":" not in l.split(": ", 1)[1] for l in lines[:-1])
