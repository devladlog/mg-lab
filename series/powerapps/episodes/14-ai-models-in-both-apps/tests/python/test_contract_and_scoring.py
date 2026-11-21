import json

import jsonschema
import pytest
import triage
from conftest import SRC

GOLDEN = SRC / "eval" / "golden.jsonl"


def good(**kw):
    o = {"summary": "Fire door wedged open.", "category": "Fire", "severity": "Major", "confidence": 80}
    o.update(kw)
    return json.dumps(o)


def test_the_contract_is_a_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(triage.SCHEMA)


def test_the_contract_enums_are_the_base_schema_choices(schema):
    item = next(t for t in schema["tables"] if t["logicalName"] == "cin_inspectionitem")
    cols = {c["logicalName"]: c for c in item["columns"]}
    assert triage.SCHEMA["properties"]["severity"]["enum"] == [o[0] for o in cols["cin_severity"]["options"]]
    assert triage.SCHEMA["properties"]["category"]["enum"] == [o[0] for o in cols["cin_category"]["options"]]


def test_sample_output_meets_the_contract():
    obj, err = triage.parse_model_text((SRC / "eval" / "sample-output.json").read_text(encoding="utf-8"))
    assert err is None and obj["severity"] == "Major"


def test_golden_set_is_small_labelled_and_covers_every_label():
    rows = triage.load_golden(GOLDEN)
    assert 12 <= len(rows) <= 20
    assert len({r["id"] for r in rows}) == len(rows)
    assert {r["severity"] for r in rows} == set(triage.SEVERITIES)
    assert {r["category"] for r in rows} == set(triage.SCHEMA["properties"]["category"]["enum"])
    assert all(len(r["notes"]) >= 8 for r in rows)
    assert any("Ignore all earlier rules" in r["notes"] for r in rows), "one prompt-injection case"


@pytest.mark.parametrize("text", [
    good(), "```json\n" + good() + "\n```", "  " + good() + "\n"])
def test_valid_answers_parse(text):
    obj, err = triage.parse_model_text(text)
    assert err is None and obj["confidence"] == 80


@pytest.mark.parametrize("text,why", [
    (None, "empty"), ("", "not json"), ("Sure! Here you go: " + good(), "not json"),
    (good(severity="Severe"), "contract"), (good(category="Plumbing"), "contract"),
    (good(confidence=101), "contract"), (good(confidence=80.5), "contract"), (good(summary=""), "contract"),
    (good(summary="x" * 241), "contract"), (json.dumps({"summary": "x", "category": "Fire", "severity": "Major"}), "contract"),
    (good()[:-1] + ', "extra": 1}', "contract")])
def test_invalid_answers_are_rejected_not_repaired(text, why):
    obj, err = triage.parse_model_text(text)
    assert obj is None and why in err


def test_a_perfect_run_scores_one():
    g = triage.load_golden(GOLDEN)
    ans = {r["id"]: good(severity=r["severity"], category=r["category"]) for r in g}
    s = triage.score(g, ans)
    assert (s["severity_accuracy"], s["category_accuracy"], s["invalid"], s["under_calls"]) == (1.0, 1.0, 0, 0)


def test_under_calling_a_major_or_critical_is_counted_but_over_calling_is_not():
    g = [{"id": "a", "notes": "x" * 10, "category": "Fire", "severity": "Critical"},
         {"id": "b", "notes": "x" * 10, "category": "Fire", "severity": "Minor"},
         {"id": "c", "notes": "x" * 10, "category": "Fire", "severity": "Major"}]
    ans = {"a": good(severity="Minor"), "b": good(severity="Critical"), "c": good(severity="Major")}
    s = triage.score(g, ans)
    assert s["under_calls"] == 1 and s["severity_correct"] == 1


def test_missing_and_malformed_answers_count_as_invalid_not_as_wrong_labels():
    g = triage.load_golden(GOLDEN)
    s = triage.score(g, {g[0]["id"]: "nope"})
    assert s["invalid"] == len(g) and s["severity_correct"] == 0
    assert s["rows"][0]["error"].startswith("not json")


def test_request_bodies_carry_the_prompt_and_the_photo_in_each_vendors_shape():
    o = triage.openai_body("triage", "Wet floor", "QUJD")
    assert o["messages"][0] == {"role": "system", "content": triage.SYSTEM_PROMPT}
    assert o["messages"][1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
    a = triage.anthropic_body("m", "Wet floor", "QUJD")
    assert a["system"] == triage.SYSTEM_PROMPT
    assert a["messages"][0]["content"][0]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}
    assert a["messages"][0]["content"][-1] == {"type": "text", "text": "Notes: Wet floor"}
    assert "image" not in json.dumps(triage.anthropic_body("m", "Wet floor"))


def test_response_readers():
    assert triage.openai_text({"choices": [{"message": {"content": "x"}}]}) == "x"
    assert triage.anthropic_text({"content": [{"type": "text", "text": "a"}, {"type": "tool_use"}, {"type": "text", "text": "b"}]}) == "ab"
    assert triage.usage({"usage": {"prompt_tokens": 3, "completion_tokens": 2}}) == (3, 2)
    assert triage.usage({"usage": {"input_tokens": 5, "output_tokens": 1}}) == (5, 1)
