"""Parser and evaluator, checked against examples and documented results on Microsoft Learn."""
import math

import pytest

from formatlint.expr import (Context, Date, FieldNotInView, FormatError, evaluate, field_refs, parse_excel,
                             to_ast)

# Pairs that Learn shows in both syntaxes (column formatting + formatting syntax reference pages).
LEARN_PAIRS = [
    ("=if([$DueDate] <= @now + 86400000, '#ff0000', '')",
     {"operator": "?", "operands": [
         {"operator": "<=", "operands": ["[$DueDate]", {"operator": "+", "operands": ["@now", 86400000]}]},
         "#ff0000", ""]}),
    ("=if([$After] > [$Before], 'SortUp', if([$After] < [$Before], 'SortDown', ''))",
     {"operator": "?", "operands": [
         {"operator": ">", "operands": ["[$After]", "[$Before]"]}, "SortUp",
         {"operator": "?", "operands": [{"operator": "<", "operands": ["[$After]", "[$Before]"]}, "SortDown", ""]}]}),
    ("=if(@me == @currentField.email, 'red', 'blue')",
     {"operator": "?", "operands": [{"operator": "==", "operands": ["@me", "@currentField.email"]}, "red", "blue"]}),
    ("=if(@currentField < 40, '#ff0000', '#00ff00')",
     {"operator": "?", "operands": [{"operator": "<", "operands": ["@currentField", 40]}, "#ff0000", "#00ff00"]}),
]


@pytest.mark.parametrize("excel,ast", LEARN_PAIRS)
def test_excel_style_parses_to_the_ast_learn_shows(excel, ast):
    assert parse_excel(excel) == ast


def ev(expr, **row):
    return evaluate(to_ast(expr), Context(row=row, current_field="X" if "X" in row else None))


@pytest.mark.parametrize("expr,expected", [
    ("=toString(45)", "45"),
    ("=Number('365')", 365),
    ("=length('Some Text')", 1),
    ("=length('')", 0),
    ("=length(45)", 1),
    ("=length(0)", 0),
    ("=indexOf('DogFood', 'Dog')", 0),
    ("=indexOf('DogFood', 'F')", 3),
    ("=indexOf('DogFood', 'f')", -1),
    ("=lastIndexOf('DogFood DogFood', 'Dog')", 8),
    ("=substring('DogFood', 3, 6)", "Foo"),
    ("=substring('DogFood', 6, 3)", "Foo"),
    ("=toLowerCase('DogFood')", "dogfood"),
    ("=abs(-45)", 45),
    ("=floor(45.5)", 45),
    ("=ceiling(45.5)", 46),
    ("=pow(2,3)", 8),
    ("=getDate(Date('12/26/1981'))", 26),
    ("=getMonth(Date('12/26/1981'))", 11),
    ("=getYear(Date('12/26/1981'))", 1981),
    ("=startsWith('DogFood', 'Dog')", True),
    ("=endsWith('DogFood', 'Dog')", False),
    ("=toLocaleDateString(addDays(Date('11/14/2021'), 3))", "11/17/2021"),
    ("=toLocaleDateString(addDays(Date('11/14/2021'), -1))", "11/13/2021"),
    ("=if(4 < 5, 'yes', 'no')", "yes"),
])
def test_documented_results(expr, expected):
    assert ev(expr) == expected


def test_number_of_a_word_is_nan():
    assert math.isnan(ev("=Number('Wowee')"))


def test_precedence_and_unary_minus():
    assert ev("=1 + 2 * 3") == 7
    assert ev("=(1 + 2) * 3") == 9
    assert ev("=[$foo] * -7", foo=3) == -21
    assert ev("=-[$foo] + 1", foo=3) == -2


def test_plus_concatenates_text():
    assert ev("='status: ' + [$Status]", Status="New") == "status: New"
    assert ev("=(20 / 250) + '%'") == "0.08%"


def test_date_math_in_milliseconds():
    d = Date.parse("2026-12-01")
    assert ev("=[$D] + 86400000", D=d) == Date.parse("2026-12-02")
    assert ev("=Number([$D])", D=d) == d.ms


def test_unknown_function_is_an_error():
    with pytest.raises(FormatError, match="today"):
        parse_excel("=if([$DueDate] < today(), 'red', '')")


def test_unbalanced_parentheses_are_an_error():
    with pytest.raises(FormatError):
        parse_excel("=if(1 < 2, 'a', 'b'")


def test_missing_field_is_reported_not_rendered_empty():
    with pytest.raises(FieldNotInView) as e:
        ev("=if([$RequestStatus] == 'Closed', '', 'red')", DueDate="x")
    assert e.value.name == "RequestStatus"


def test_field_refs():
    ast = parse_excel("=if([$DueDate] <= @now && [$Requester.email] == @me, @currentField, '')")
    assert field_refs(ast) == {"DueDate", "Requester", "@currentField"}
