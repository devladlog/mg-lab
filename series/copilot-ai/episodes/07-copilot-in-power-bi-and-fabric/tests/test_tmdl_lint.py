import json
import textwrap

import pytest

from conftest import CATEGORY_MODEL, DATA
from copilot_pbi import describe, lint, tmdl

SAMPLE = textwrap.dedent("""\
    /// Fact table, one row per order line.
    table Sales

    \tmeasure 'Sales Amount' = SUMX(Sales, Sales[Quantity] * Sales[Unit Price])
    \t\tformatString: #,0.00

    \t/// Margin amount.
    \tmeasure Margin = ```
    \t\t\t[Sales Amount] - [Total Cost]
    \t\t\t```
    \t\tformatString: #,0.00

    \tcolumn CustNo
    \t\tdataType: int64
    \t\tsummarizeBy: sum
    \t\tsourceColumn: CustNo

    \tcolumn 'Order Number'
    \t\tdataType: string
    \t\tisHidden
    \t\tsummarizeBy: none

    \tpartition Sales = m
    \t\tmode: import
    \t\tsource =
    \t\t\t\tlet
    \t\t\t\t    Source = 1
    \t\t\t\tin
    \t\t\t\t    Source

    table Dim_Store
    \tcolumn Country
    \t\tdataType: string
    \tcolumn StoreID
    \t\tdataType: int64
    """)


def model_from(text):
    m = tmdl.Model()
    m.tables = tmdl.parse_table_text(text)
    return m


def test_parser_reads_objects_descriptions_and_flags():
    m = model_from(SAMPLE)
    sales = m.table("Sales")
    assert sales.description == "Fact table, one row per order line."
    assert [x.name for x in sales.measures] == ["Sales Amount", "Margin"]
    assert sales.measures[1].description == "Margin amount."
    assert sales.measures[0].format_string == "#,0.00"
    cols = {c.name: c for c in sales.columns}
    assert cols["Order Number"].hidden and not cols["CustNo"].hidden
    assert cols["CustNo"].summarize_by == "sum" and cols["CustNo"].data_type == "int64"
    # the partition's M code and the fenced DAX expression must not leak into columns or measures
    assert len(sales.columns) == 2 and len(sales.measures) == 2


def test_quoted_names_with_escaped_quote():
    name, rest = tmdl.split_name("'Owner''s Margin' = 1")
    assert name == "Owner's Margin" and rest == "= 1"


def test_lint_finds_documented_problems():
    findings = lint.lint_model(model_from(SAMPLE))
    rules = {(f.rule, f.where) for f in findings}
    assert ("C001", "measure [Sales Amount]") in rules                    # no description
    assert ("C001", "measure [Margin]") not in rules                      # has one
    assert ("C002", "table Dim_Store") in rules
    assert ("C004", "column Sales[CustNo]") in rules                      # abbreviation / CamelCase
    assert ("C004", "table Dim_Store") not in rules                       # tables are not name-checked
    assert ("C005", "column Dim_Store[StoreID]") in rules                 # visible key
    assert ("C006", "column Sales[CustNo]") in rules                      # implicit aggregation
    assert ("C010", "model") in rules


def test_description_longer_than_200_characters_is_flagged():
    long = "x" * 201
    text = f"/// {long}\ntable T\n"
    findings = lint.lint_model(model_from(text))
    assert any(f.rule == "C003" and "201" in f.message for f in findings)
    assert not any(f.rule == "C003" for f in lint.lint_model(model_from("/// " + "x" * 200 + "\ntable T\n")))


def test_duplicate_column_name_flag_goes_away_with_descriptions():
    two = "/// a\ntable A\n\t/// first\n\tcolumn Country\n\t\tdataType: string\n/// b\ntable B\n\tcolumn Country\n\t\tdataType: string\n"
    assert any(f.rule == "C009" for f in lint.lint_model(model_from(two)))
    both = "/// a\ntable A\n\t/// first\n\tcolumn Country\n\t\tdataType: string\n/// b\ntable B\n\t/// second\n\tcolumn Country\n\t\tdataType: string\n"
    assert not any(f.rule == "C009" for f in lint.lint_model(model_from(both)))


def test_cryptic_names():
    assert lint.cryptic("ProdID") and lint.cryptic("Cust_No") and lint.cryptic("Col1") and lint.cryptic("ab")
    assert lint.cryptic("Sales Amount") is None and lint.cryptic("Margin %") is None and lint.cryptic("Order Number") is None


def test_instruction_checks():
    m = model_from(SAMPLE)
    text = "Use [Sales Amount] for revenue. Use 'Sales'[Order Number] to count. Use [Revenue Net] and 'Sales'[Nope]. See Dim_Store[Country]."
    findings = lint.lint_instructions(m, text)
    by = {(f.rule, f.where) for f in findings}
    assert ("A003", "[Revenue Net]") in by
    assert ("A003", "'Sales'[Nope]") in by
    assert ("A004", "'Sales'[Order Number]") in by      # hidden column
    assert not any(w == "[Sales Amount]" or "Country" in w for _, w in by)
    assert lint.lint_instructions(m, "  ")[0].rule == "A001"
    big = lint.lint_instructions(m, "a" * (lint.AI_INSTRUCTIONS_MAX_CHARS + 1))
    assert big[0].rule == "A002" and big[0].severity == "error"
    assert lint.lint_instructions(m, "a" * lint.AI_INSTRUCTIONS_MAX_CHARS) == []


def test_verified_answer_limits():
    ok = {"verifiedAnswers": [{"visual": "v", "triggerPhrases": ["a", "b"]}]}
    assert lint.lint_verified(ok) == []
    too_many = {"verifiedAnswers": [{"visual": f"v{i}", "triggerPhrases": [f"p{i}"]} for i in range(251)]}
    assert [f.rule for f in lint.lint_verified(too_many)] == ["V001"]
    f = lint.lint_verified({"verifiedAnswers": [{"visual": "v", "triggerPhrases": [str(i) for i in range(16)] + ["x" * 501]}]})
    assert {x.rule for x in f} == {"V002", "V003"}
    dup = lint.lint_verified({"verifiedAnswers": [{"visual": "a", "triggerPhrases": ["Sales by Year"]},
                                                   {"visual": "b", "triggerPhrases": ["sales  by year"]}]})
    assert [x.rule for x in dup] == ["V004"]
    assert lint.lint_verified({"verifiedAnswers": [{"visual": "a", "triggerPhrases": []}]})[0].rule == "V005"


# ---- the real category model (Power BI episode 1) before and after the Copilot preparation ----

pytestmark_cat = pytest.mark.skipif(not CATEGORY_MODEL.exists(), reason="Power BI episode 1 model not in this checkout")


@pytestmark_cat
def test_real_model_before_preparation_has_the_expected_findings():
    m = tmdl.load_model(CATEGORY_MODEL)
    assert len(m.tables) == 5 and len(m.measures()) == 6
    f = lint.lint_model(m)
    assert sum(1 for x in f if x.rule == "C001") == 6          # none of the six measures has a description
    assert sum(1 for x in f if x.rule == "C009") == 1          # Country in Customer and Store
    assert lint.summarise(f)["error"] == 0


@pytestmark_cat
def test_real_model_after_preparation_is_clean(tmp_path):
    out = tmp_path / "ContosoSales.SemanticModel"
    spec = describe.load_spec(DATA / "descriptions-contoso-bikes.json")
    assert describe.apply_descriptions(CATEGORY_MODEL, out, spec) == 9
    m = tmdl.load_model(out)
    text = (DATA / "ai-instructions-contoso-bikes.md").read_text(encoding="utf-8")
    plan = json.loads((DATA / "verified-answers-plan.json").read_text(encoding="utf-8"))
    findings = lint.lint_model(m) + lint.lint_instructions(m, text) + lint.lint_verified(plan)
    assert findings == [], [str(x) for x in findings]
    assert len(m.measures()) == 7 and m.table("Sales").measures[0].name == "Orders Shipped"
    assert len(text) < lint.AI_INSTRUCTIONS_MAX_CHARS


@pytestmark_cat
def test_instructions_without_the_new_measure_fail_on_the_unprepared_model():
    m = tmdl.load_model(CATEGORY_MODEL)
    text = (DATA / "ai-instructions-contoso-bikes.md").read_text(encoding="utf-8")
    errors = [f for f in lint.lint_instructions(m, text) if f.severity == "error"]
    assert [f.where for f in errors] == ["[Orders Shipped]"]


@pytestmark_cat
def test_describe_never_changes_the_source_and_refuses_to_overwrite(tmp_path):
    before = {p: p.read_bytes() for p in CATEGORY_MODEL.rglob("*") if p.is_file()}
    out = tmp_path / "copy"
    describe.apply_descriptions(CATEGORY_MODEL, out, describe.load_spec(DATA / "descriptions-contoso-bikes.json"))
    assert before == {p: p.read_bytes() for p in CATEGORY_MODEL.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        describe.apply_descriptions(CATEGORY_MODEL, out, {"tables": {}, "measures": {}, "columns": {}})
    # an object that already has a description is left alone
    out2 = tmp_path / "copy2"
    assert describe.apply_descriptions(out, out2, {"measures": {"Sales[Units]": "again"}}) == 0
    assert "again" not in (out2 / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
