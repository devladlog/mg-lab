"""Every function the digest uses, checked against the examples in the Learn functions reference.

Each row is (expression, documented result). The comment names the reference entry. Rows marked
'repo' are our own cases (edge cases the flow depends on), not Learn examples.
"""
import pytest

from flowkit.expr import Context, ExpressionError, evaluate

from conftest import SUMMER_RUN

PRODUCE = ('<?xml version="1.0"?><produce><item><name>Gala</name><type>apple</type><count>20</count></item>'
           '<item><name>Honeycrisp</name><type>apple</type><count>10</count></item></produce>')


@pytest.fixture
def ctx():
    return Context(now=SUMMER_RUN, parameters={"items": PRODUCE})


@pytest.mark.parametrize("expression, expected", [
    # strings
    ("indexOf('hello world', 'world')", 6),                                   # indexOf
    ("indexOf('Hello World', 'WORLD')", 6),                                   # indexOf "isn't case-sensitive"
    ("lastIndexOf('hello world hello world', 'world')", 18),                  # lastIndexOf
    ("lastIndexOf('hello world hello world', '')", 22),                       # lastIndexOf, empty substring
    ("substring('hello world', 6, 5)", "world"),                              # substring
    ("slice('Hello World', 2)", "llo World"),                                 # slice examples
    ("slice('Hello World', 30)", ""),
    ("slice('Hello World', 10, 2)", ""),
    ("slice('Hello World', -2)", "ld"),
    ("slice('Hello World', 3, -1)", "lo Worl"),
    ("slice('Hello World', 6, 20)", "World"),
    ("split('a_b_c', '_')", ["a", "b", "c"]),                                 # split example 1
    ("split('a_b_c', ' ')", ["a_b_c"]),                                       # split example 2
    ("join(createArray('a', 'b', 'c'), '.')", "a.b.c"),                       # join
    ("isInt('10')", True),                                                    # isInt
    ("isFloat('10,000.00')", True),                                           # isFloat example 1
    ("isFloat('10.000,00', 'de-DE')", True),                                  # isFloat example 2
    # numbers
    ("formatNumber(1234567890, '#,##0.00', 'en-US')", "1,234,567,890.00"),    # formatNumber example 1
    ("formatNumber(1234567890, '#,##0.00', 'is-IS')", "1.234.567.890,00"),    # formatNumber example 2
    ("formatNumber(17.35, 'C2')", "$17.35"),                                  # formatNumber example 3
    ("formatNumber(17.35, 'C2', 'is-IS')", "17,35 kr"),                       # formatNumber example 4
    ("formatNumber(42, '00000')", "00042"),                                   # repo: reference numbers
    ("formatNumber(4350.5, '#,##0.00', 'en-US')", "4,350.50"),                # repo
    ("div(11, 5)", 2),                                                        # div example 1 (integer)
    ("div(11, 5.0)", 2.2),                                                    # div example 2 (float)
    # collections
    ("take('abcde', 3)", "abc"),                                              # take
    ("take(createArray(0, 1, 2, 3, 4), 3)", [0, 1, 2]),
    ("skip(createArray(0, 1, 2, 3), 1)", [1, 2, 3]),                          # skip
    ("sort(createArray(2, 1, 0, 3))", [0, 1, 2, 3]),                          # sort example 1
    ("reverse(createArray(0, 1, 2, 3))", [3, 2, 1, 0]),                       # reverse
    ("union(createArray(1, 2, 3), createArray(1, 2, 10, 101))", [1, 2, 3, 10, 101]),   # union
    ("intersection(createArray(1, 2, 3), createArray(101, 2, 1, 10), createArray(6, 8, 1, 2))", [1, 2]),
    ("chunk('abcdefghijklmnopqrstuvwxyz', 10)", ["abcdefghij", "klmnopqrst", "uvwxyz"]),  # chunk
    ("chunk(createArray(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12), 5)", [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10], [11, 12]]),
    # dates and time zones
    ("convertFromUtc('2018-01-01T08:00:00.0000000Z', 'Pacific Standard Time')", "2018-01-01T00:00:00.0000000"),
    ("convertFromUtc('2018-01-01T08:00:00.0000000Z', 'Pacific Standard Time', 'D')", "Monday, January 1, 2018"),
    ("convertTimeZone('2018-01-01T08:00:00.0000000Z', 'UTC', 'Pacific Standard Time')", "2018-01-01T00:00:00.0000000"),
    ("convertToUtc('01/01/2018 00:00:00', 'Pacific Standard Time')", "2018-01-01T08:00:00.0000000Z"),
    ("startOfDay('2018-03-15T13:30:30Z')", "2018-03-15T00:00:00.0000000Z"),   # startOfDay
    ("dayOfWeek('2018-03-15T13:27:36Z')", 4),                                 # dayOfWeek (Sunday is 0)
    ("dayOfYear('2018-03-15T13:27:36Z')", 74),                                # dayOfYear
    ("dateDifference('2015-02-08', '2018-07-30')", "1268.00:00:00"),          # dateDifference
    ("formatDateTime('03/15/2018')", "2018-03-15T00:00:00.0000000"),          # formatDateTime examples
    ("formatDateTime('03/15/2018 12:00:00', 'yyyy-MM-ddTHH:mm:ss')", "2018-03-15T12:00:00"),
    ("formatDateTime('01/31/2016', 'dddd MMMM d')", "Sunday January 31"),
    ("formatDateTime('01/31/2016', 'dddd MMMM d', 'fr-FR')", "dimanche janvier 31"),
    ("formatDateTime('01/31/2016', 'dddd MMMM d', 'es-es')", "domingo enero 31"),
    # Lisbon is 'GMT Standard Time' (Windows id): UTC+0 in winter, UTC+1 in summer
    ("convertFromUtc('2026-01-12T07:00:00Z', 'GMT Standard Time', 'HH:mm')", "07:00"),   # repo
    ("convertFromUtc('2026-07-13T06:00:00Z', 'GMT Standard Time', 'HH:mm')", "07:00"),   # repo
])
def test_reference_examples(ctx, expression, expected):
    assert evaluate(expression, ctx) == expected


def test_sort_objects_by_key(ctx):  # sort example 2
    result = evaluate("sort(createArray(json('{ \"first\": \"Amalie\", \"last\": \"Rose\" }'), "
                      "json('{ \"first\": \"Elise\", \"last\": \"Renee\" }')), 'last')", ctx)
    assert [p["first"] for p in result] == ["Elise", "Amalie"]


def test_xpath_values_and_sum(ctx):  # xpath examples 1 and 7
    assert evaluate("xpath(xml(parameters('items')), '/produce/item/name/text()')", ctx) == ["Gala", "Honeycrisp"]
    assert evaluate("xpath(xml(parameters('items')), 'sum(/produce/item/count)')", ctx) == 30


def test_xml_from_object_and_from_array_wrapped_in_a_root(ctx):  # xml examples 3 and 4 (option 4)
    assert evaluate("string(xml(json('{\"person\": {\"name\": \"Sophia Owen\", \"city\": \"Seattle\"}}')))", ctx) \
        == "<person><name>Sophia Owen</name><city>Seattle</city></person>"
    people = "json('[{\"ID\": 1, \"Name\": \"James\"}, {\"ID\": 2, \"Name\": \"John\"}]')"
    assert evaluate(f"string(xml(addProperty(json('{{}}'), 'root', addProperty(json('{{}}'), 'array', {people}))))", ctx) \
        == "<root><array><ID>1</ID><Name>James</Name></array><array><ID>2</ID><Name>John</Name></array></root>"


def test_xml_refuses_a_raw_array(ctx):  # "The function doesn't accept a raw array as input"
    with pytest.raises(ExpressionError, match="one root property|array"):
        evaluate("xml(json('[1, 2, 3]'))", ctx)


def test_substring_out_of_range_is_an_error(ctx):  # substring: "Otherwise, you get an error"
    with pytest.raises(ExpressionError, match="within the string"):
        evaluate("substring('hello', 2, 10)", ctx)


def test_unknown_time_zone_is_refused(ctx):
    with pytest.raises(ExpressionError, match="Windows time zone"):
        evaluate("convertFromUtc(utcNow(), 'Europe/Lisbon')", ctx)
