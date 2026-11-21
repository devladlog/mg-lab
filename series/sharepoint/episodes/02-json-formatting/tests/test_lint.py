from collections import Counter

from formatlint.__main__ import main
from formatlint.lint import lint_format, lint_map
from conftest import SRC


def test_our_formats_are_clean():
    assert lint_map(SRC / "formats" / "map.json") == []


def test_bad_examples_hit_every_rule():
    rules = Counter(f.rule for f in lint_map(SRC / "formats" / "bad" / "map.json"))
    assert rules == Counter({"FL006": 5, "FL001": 1, "FL003": 1, "FL004": 1, "FL005": 1, "FL007": 1, "FL008": 1, "FL009": 1, "FL010": 1})


def test_column_format_must_have_its_fields_in_every_view_that_shows_it():
    f = [x for x in lint_map(SRC / "formats" / "bad" / "map.json") if x.file.endswith("due-date.column.json")]
    assert len(f) == 1
    assert "RequestStatus" in f[0].message and "Due dates only" in f[0].message


def test_mailto_and_field_links_are_allowed():
    fmt = {"$schema": "https://developer.microsoft.com/json-schemas/sp/v2/column-formatting.schema.json",
           "elmType": "a", "txtContent": "@currentField.title",
           "attributes": {"href": "='mailto:' + @currentField.email"}}
    assert lint_format(fmt, "x", "column", {"V": ["Requester"]}, "Requester") == []
    fmt["attributes"]["href"] = "='ftp://files/' + @currentField.email"
    assert [x.rule for x in lint_format(fmt, "x", "column", {"V": ["Requester"]}, "Requester")] == ["FL008"]


def test_cli_exit_codes(capsys):
    assert main(["lint", str(SRC / "formats" / "map.json")]) == 0
    assert main(["lint", str(SRC / "formats" / "bad" / "map.json")]) == 1
    assert "10 error(s), 3 warning(s)" in capsys.readouterr().out
