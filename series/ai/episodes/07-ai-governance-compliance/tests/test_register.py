from datetime import date

import pytest
import yaml

from aigov import register


def test_repo_register_is_valid(register_path):
    systems = register.load(register_path)
    assert set(systems) == {"hr-bot", "ap-agent", "helpdesk-triage"}
    hr = systems["hr-bot"]
    assert hr.tier == "high" and hr.uses_retrieval and hr.data_residency == "eu"
    assert ("gpt-5-mini", "2025-08-07") in hr.approved_models
    assert isinstance(hr.next_review, date) and hr.rai_gate["verdict"] == "PASS"


def base(**over):
    e = {"id": "x", "name": "X", "owner": "Riley Demo", "purpose": "p", "tier": "low",
         "approved_models": [{"name": "gpt-5-mini", "version": "2025-08-07"}], "next_review": "2027-01-01"}
    e.update(over)
    return e


def test_all_problems_are_reported_at_once():
    data = {"systems": [
        base(id="a", tier="critical"),
        base(id="b", approved_models=[{"name": "gpt-5-mini"}]),          # unpinned version
        base(id="c", tier="high", human_oversight=""),                    # high needs oversight
        base(id="d", next_review="next spring"),
        base(id="a"),                                                     # duplicate id
        {"id": "e", "name": "E"},                                         # missing fields
    ]}
    with pytest.raises(register.RegisterError) as e:
        register.parse(data)
    msg = str(e.value)
    for expected in ("tier must be one of", "pin the version", "requires a human_oversight", "not a YYYY-MM-DD",
                     "duplicate id 'a'", "missing owner, purpose, tier, approved_models, next_review"):
        assert expected in msg


def test_rai_gate_verdict_and_date_are_validated():
    with pytest.raises(register.RegisterError, match="verdict must be PASS or FAIL"):
        register.parse({"systems": [base(rai_gate={"date": "2026-11-01", "verdict": "ok"})]})
    s = register.parse({"systems": [base(rai_gate={"date": "2026-11-01", "verdict": "PASS"})]})["x"]
    assert s.rai_gate["date"] == date(2026, 11, 1)


def test_empty_register_is_rejected():
    with pytest.raises(register.RegisterError, match="non-empty list"):
        register.parse(yaml.safe_load("version: 1\nsystems: []\n"))
