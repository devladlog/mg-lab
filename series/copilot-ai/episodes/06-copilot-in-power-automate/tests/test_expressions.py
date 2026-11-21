from copilot_flow_review.expressions import check_date_format, check_expression, known_functions, strip_wrapper
from conftest import ROOT


def codes(expr):
    return [(f.code, f.severity) for f in check_expression(expr)]


def test_function_list_comes_from_learn_and_has_the_functions_used_here():
    names = known_functions()
    assert len(names) >= 130
    for n in ("concat", "formatDateTime", "substring", "string", "length", "sub", "utcNow", "triggerBody", "parameters", "workflow"):
        assert n.lower() in names
    header = (ROOT / "src" / "data" / "wdl-functions.txt").read_text(encoding="utf-8")
    assert "learn.microsoft.com/azure/logic-apps/workflow-definition-language-functions-reference" in header


def test_learn_expression_assistant_examples_written_by_hand_pass():
    # The prompts are from "Create, update, and fix expressions with Copilot expression assistant".
    # The expressions are written by hand here (not Copilot output): they only show what the checker accepts.
    assert codes("concat(triggerBody()?['firstName'], ' ', triggerBody()?['lastName'])") == []
    assert codes("substring(string(triggerBody()?['phone']), sub(length(string(triggerBody()?['phone'])), 4))") == []
    assert codes("string(triggerBody()?['phone'])") == []
    assert codes("formatDateTime(triggerBody()?['TriggerDate'], 'dd-MM')") == []


def test_the_DD_MM_prompt_from_learn_is_a_trap_when_written_literally():
    # Learn's sample prompt says: Format TriggerDate to 'DD-MM' format.
    # formatDateTime takes a .NET custom pattern, and D is not a specifier there.
    found = check_expression("formatDateTime(triggerBody()?['TriggerDate'], 'DD-MM')")
    assert [f.code for f in found] == ["EX003"]
    assert "dd" in found[0].message


def test_missing_parenthesis_like_the_learn_example_is_an_error():
    # Learn shows a missing closing parenthesis after 'Phone' in variables(...).
    found = check_expression("concat(variables('Phone')")
    assert [f.code for f in found] == ["EX001"]
    assert "never closed" in found[0].message


def test_unterminated_string_and_stray_bracket():
    assert [f.code for f in check_expression("concat('a, 'b')")] == ["EX001"]
    assert [f.code for f in check_expression("length(x))")] == ["EX001"]
    assert [f.code for f in check_expression("items('x')?['a'")] == ["EX001"]


def test_unknown_function_is_an_error_and_wrong_case_is_a_note():
    assert codes("frobnicate(1)") == [("EX002", "error")]
    assert codes("formatdatetime(utcNow(), 'yyyy-MM-dd')") == [("EX002", "info")]


def test_doubled_single_quote_is_an_escaped_quote_not_the_end_of_the_string():
    assert codes("concat('it''s', ' ok')") == []


def test_wrappers_are_accepted():
    assert strip_wrapper("@concat('a','b')") == "concat('a','b')"
    assert strip_wrapper("@{concat('a','b')}") == "concat('a','b')"
    assert strip_wrapper("@@literal") == "@@literal"
    assert codes("@{concat('a','b')}") == []


def test_date_format_rules():
    assert [f.code for f in check_date_format("DD-MM-YYYY")] == ["EX003"]
    assert [f.code for f in check_date_format("yyyy-mm-dd")] == ["EX004"]
    assert check_date_format("yyyy-MM-ddTHH:mm:ss") == []   # the T is a literal on purpose (example on Learn)
    assert check_date_format("dddd MMMM d") == []           # example on Learn
    assert check_date_format("D") == []                     # single character = standard specifier (long date)
    assert check_date_format("o") == []


def test_only_the_format_argument_is_checked():
    # 'DueDate' and a time zone name contain capital D and S but are not formats.
    assert codes("formatDateTime(items('x')?['DueDate'], 'dd-MM-yyyy')") == []
    assert codes("convertTimeZone(utcNow(), 'UTC', 'Pacific Standard Time', 'yyyy-MM-dd')") == []
    assert codes("convertTimeZone(utcNow(), 'UTC', 'Pacific Standard Time', 'YYYY-MM-DD')") == [("EX003", "warning")]
