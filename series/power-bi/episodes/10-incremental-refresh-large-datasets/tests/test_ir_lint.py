import ir_lint
from conftest import MODEL


def rules(definition):
    return [f["rule"] for f in ir_lint.check(definition)]


def edit(root, rel, old, new, count=1):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert old in t, old
    p.write_text(t.replace(old, new, count if count else -1), encoding="utf-8")


SALES = "tables/Sales.tmdl"


def test_the_lab_model_is_clean():
    assert ir_lint.check(MODEL) == []
    assert ir_lint.main([str(MODEL), "--strict"]) == 0


def test_a_model_without_a_policy_has_nothing_to_check(model_copy):
    t = (model_copy / SALES).read_text(encoding="utf-8")
    start = t.index("\trefreshPolicy")
    end = t.index("\tcolumn 'Order Number'")
    (model_copy / SALES).write_text(t[:start] + t[end:], encoding="utf-8")
    assert rules(model_copy) == []


def test_IR001_wrong_case_and_missing_parameter(model_copy):
    edit(model_copy, "expressions.tmdl", "expression RangeStart =", "expression rangeStart =")
    f = ir_lint.check(model_copy)
    assert [x["rule"] for x in f] == ["IR001"] and "wrong case" in f[0]["message"]
    edit(model_copy, "expressions.tmdl", "expression RangeEnd =", "expression Range_End =")
    assert rules(model_copy).count("IR001") == 2


def test_IR002_parameter_that_is_not_datetime(model_copy):
    edit(model_copy, "expressions.tmdl", 'RangeEnd = #datetime(2026, 11, 8, 0, 0, 0) meta [IsParameterQuery=true, Type="DateTime"',
         'RangeEnd = "2026-11-08" meta [IsParameterQuery=true, Type="Text"')
    assert rules(model_copy) == ["IR002"]


def test_IR003_equals_on_both_ends(model_copy):
    edit(model_copy, SALES, "< RangeEnd", "<= RangeEnd", count=0)
    assert rules(model_copy) == ["IR003"]


def test_IR003_strictly_greater_on_the_start(model_copy):
    edit(model_copy, SALES, ">= RangeStart", "> RangeStart", count=0)
    assert "IR003" in rules(model_copy)


def test_IR003_accepts_the_reversed_but_equivalent_form(model_copy):
    edit(model_copy, SALES, "[OrderTimestamp] >= RangeStart and [OrderTimestamp] < RangeEnd", "RangeStart <= [OrderTimestamp] and [OrderTimestamp] < RangeEnd", count=0)
    assert rules(model_copy) == []


def test_IR004_partition_that_ignores_the_parameters(model_copy):
    t = (model_copy / SALES).read_text(encoding="utf-8")
    head, part = t.split("\tpartition Sales = m")
    part = part.replace("each [OrderTimestamp] >= RangeStart and [OrderTimestamp] < RangeEnd", "each [Quantity] > 0")
    (model_copy / SALES).write_text(head + "\tpartition Sales = m" + part, encoding="utf-8")
    assert "IR004" in rules(model_copy)


def test_IR005_refresh_period_not_shorter_than_the_store_period(model_copy):
    edit(model_copy, SALES, "incrementalGranularity: day", "incrementalGranularity: year")
    edit(model_copy, SALES, "incrementalPeriods: 10", "incrementalPeriods: 3")
    f = [x for x in ir_lint.check(model_copy) if x["rule"] == "IR005"]
    assert f and "shorter" in f[0]["message"]


def test_IR006_a_source_without_folding(model_copy):
    edit(model_copy, SALES, "Sql.Database(SqlServer, SqlDatabase)", "Csv.Document(Web.Contents(SqlServer))", count=0)
    assert rules(model_copy).count("IR006") >= 1


def test_IR007_buffering_before_the_filter(model_copy):
    edit(model_copy, SALES, "Sales = Source{[Schema = \"dbo\", Item = \"Sales\"]}[Data],\n\t\t\t\t    InPeriod",
         "Sales = Table.Buffer(Source{[Schema = \"dbo\", Item = \"Sales\"]}[Data]),\n\t\t\t\t    InPeriod", count=0)
    assert "IR007" in rules(model_copy)


def test_IR008_filter_on_a_column_that_is_not_datetime(model_copy):
    edit(model_copy, SALES, "sourceColumn: OrderTimestamp", "sourceColumn: OrderTimestamp\n\t\tannotation x = y")
    edit(model_copy, SALES, "\t\tdataType: dateTime\n\t\tformatString: yyyy-mm-dd hh:mm:ss\n\t\tsummarizeBy: none\n\t\tsourceColumn: OrderTimestamp",
         "\t\tdataType: string\n\t\tsummarizeBy: none\n\t\tsourceColumn: OrderTimestamp")
    assert "IR008" in rules(model_copy)


def test_IR009_detect_data_changes_on_the_filter_column(model_copy):
    edit(model_copy, SALES, "List.Max(InPeriod[ModifiedDate])", "List.Max(InPeriod[OrderTimestamp])")
    assert rules(model_copy) == ["IR009"]


def test_IR010_polling_column_not_in_the_model(model_copy):
    edit(model_copy, SALES, "sourceColumn: ModifiedDate", "sourceColumn: ModifiedStamp")
    assert rules(model_copy) == ["IR010"]


def test_IR011_no_polling_expression(model_copy):
    t = (model_copy / SALES).read_text(encoding="utf-8")
    a = t.index("\t\tpollingExpression =")
    b = t.index("\t\tsourceExpression =")
    (model_copy / SALES).write_text(t[:a] + t[b:], encoding="utf-8")
    f = ir_lint.check(model_copy)
    assert [x["rule"] for x in f] == ["IR011"] and f[0]["severity"] == "warning"
    assert ir_lint.main([str(model_copy)]) == 0 and ir_lint.main([str(model_copy), "--strict"]) == 1
