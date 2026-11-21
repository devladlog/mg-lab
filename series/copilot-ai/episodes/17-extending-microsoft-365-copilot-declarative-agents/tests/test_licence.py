import json

import pytest

from dakit import licence
from dakit.cli import main
from conftest import PACKAGE, SRC

SAMPLE = SRC / "samples" / "declarativeAgent.with-knowledge.json"


def test_vendor_desk_needs_no_licence():
    r = licence.assess_file(PACKAGE / "declarativeAgent.json")
    assert r["needs"] == "all"
    assert {x["item"] for x in r["rows"]} == {"actions", "instructions"}


def test_sharepoint_needs_billing_or_licence_and_email_needs_licence():
    r = licence.assess({"instructions": "x", "capabilities": [{"name": "OneDriveAndSharePoint"}]})
    assert r["needs"] == "payg"
    r = licence.assess_file(SAMPLE)
    assert r["needs"] == "licensed"
    assert {x["item"]: x["tier"] for x in r["rows"]}["OneDriveAndSharePoint"] == "payg"


@pytest.mark.parametrize("cap,tier", [("WebSearch", "all"), ("GraphicArt", "all"), ("CodeInterpreter", "all"),
                                      ("GraphConnectors", "payg"), ("EmbeddedKnowledge", "payg"), ("Dataverse", "payg"),
                                      ("Email", "licensed"), ("People", "licensed"), ("TeamsMessages", "licensed"), ("Meetings", "licensed")])
def test_table_rows(cap, tier):
    assert licence.assess({"capabilities": [{"name": cap}]})["needs"] == tier


def test_capabilities_missing_from_the_table_are_reported_not_guessed():
    r = licence.assess({"capabilities": [{"name": "EmailActions"}, {"name": "CodeInterpreter"}]})
    assert r["unlisted"] == ["EmailActions"] and r["needs"] == "all"
    assert "not in Learn's licensing table" in licence.render(r)


def test_sample_is_schema_valid():
    from dakit.validate import schema_findings
    assert schema_findings(json.loads(SAMPLE.read_text()), "agent", "sample") == []


def test_cli_max_gate(capsys):
    assert main(["licence", str(PACKAGE / "declarativeAgent.json"), "--max", "all"]) == 0
    assert main(["licence", str(SAMPLE), "--max", "payg"]) == 1
    assert "FAIL: needs licensed, allowed payg" in capsys.readouterr().out
    assert main(["licence", str(SAMPLE)]) == 0
