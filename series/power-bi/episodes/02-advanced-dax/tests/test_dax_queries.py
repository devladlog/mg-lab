"""The saved DAX query view files and their expected results stay in sync."""
import csv
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
QUERIES = SRC / "ContosoSales.SemanticModel" / "DAXQueries"
EXPECTED = SRC / "reference" / "expected"

QUERY_FILES = sorted(QUERIES.glob("*.dax"))


def test_every_query_has_expected_results_and_vice_versa():
    assert {q.stem for q in QUERY_FILES} == {e.stem for e in EXPECTED.glob("*.csv")}
    assert len(QUERY_FILES) == 5


@pytest.mark.parametrize("query", QUERY_FILES, ids=lambda p: p.stem)
def test_expected_header_matches_the_query_columns(query):
    text = query.read_text(encoding="utf-8")
    body = text[text.index("SUMMARIZECOLUMNS("):]
    group_by = re.findall(r"^\s*'[^']+'\[([^\]]+)\],\s*$", body, flags=re.M)
    names = re.findall(r'^\s*"([^"]+)",', body, flags=re.M)
    with open(EXPECTED / f"{query.stem}.csv", newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == group_by + names


@pytest.mark.parametrize("query", QUERY_FILES, ids=lambda p: p.stem)
def test_queries_are_evaluate_statements_with_an_order_by(query):
    text = query.read_text(encoding="utf-8")
    assert re.search(r"^EVALUATE$", text, flags=re.M)
    assert re.search(r"^ORDER BY ", text, flags=re.M)
    assert text.lstrip().startswith("//")          # one-line comment says what the query shows


def test_query_defined_measures_are_not_in_the_model():
    model = (SRC / "ContosoSales.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text()
    for q in QUERY_FILES:
        for name in re.findall(r"MEASURE\s+Sales\[([^\]]+)\]", q.read_text()):
            assert f"measure '{name}'" not in model and f"measure {name} " not in model, name
