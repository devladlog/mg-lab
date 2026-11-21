import copy

import pytest

from triage.schema import TRIAGE_SCHEMA, response_format, strict_schema_problems


def test_triage_schema_fits_the_strict_subset():
    assert strict_schema_problems(TRIAGE_SCHEMA) == []


def test_missing_additional_properties_is_reported():
    s = copy.deepcopy(TRIAGE_SCHEMA)
    del s["additionalProperties"]
    assert any("additionalProperties" in p for p in strict_schema_problems(s))


def test_optional_property_is_reported():
    s = copy.deepcopy(TRIAGE_SCHEMA)
    s["required"].remove("summary")
    assert any("missing: summary" in p for p in strict_schema_problems(s))


def test_unsupported_string_keyword_is_reported():
    s = copy.deepcopy(TRIAGE_SCHEMA)
    s["properties"]["summary"]["maxLength"] = 120
    assert strict_schema_problems(s) == ["$.summary: 'maxLength' is not supported for string"]


def test_root_anyof_is_reported():
    assert "$: the root object can't be anyOf" in strict_schema_problems({"anyOf": [TRIAGE_SCHEMA]})


def test_nesting_deeper_than_five_levels_is_reported():
    node = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    root = node
    for i in range(6):
        child = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        node["properties"][f"l{i}"] = child
        node["required"].append(f"l{i}")
        node = child
    assert any("nesting deeper" in p for p in strict_schema_problems(root))


def test_response_format_shape():
    rf = response_format()
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "ticket_triage"


def test_response_format_refuses_a_bad_schema():
    s = copy.deepcopy(TRIAGE_SCHEMA)
    s["properties"]["priority"]["pattern"] = "^P[1-4]$"
    with pytest.raises(ValueError, match="pattern"):
        response_format(s)
