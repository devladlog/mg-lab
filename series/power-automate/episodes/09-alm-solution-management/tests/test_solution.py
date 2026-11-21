"""The two releases are valid solutions and their flows run (dry-run with mocks) the way we claim."""
import json
from datetime import datetime, timezone

import pytest
from conftest import RELEASE_1_0, SOLUTION

from almkit import checks, load_solution
from flowkit.lint import lint, load_flow
from flowkit.sim import run_flow

ACK = next((SOLUTION / "Workflows").glob("AcknowledgeITrequest-*.json"))
STALE = next((RELEASE_1_0 / "Workflows").glob("Weeklystalesummary-*.json"))
NOW = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)


def test_current_release_has_no_findings():
    sol = load_solution(SOLUTION)
    assert (sol.unique_name, sol.version_text, sol.managed, sol.prefix) == ("ITRequestNotices", "1.1.0.0", "2", "cts")
    assert checks.check_solution(sol) == []


def test_first_release_has_no_findings():
    sol = load_solution(RELEASE_1_0)
    assert sol.version_text == "1.0.0.0" and len(sol.flows) == 2 and len(sol.env_vars) == 5
    assert checks.check_solution(sol) == []


@pytest.mark.parametrize("path", [ACK, STALE], ids=["acknowledge", "stale"])
def test_flowkit_lint_is_clean(path):
    errors = [f for f in lint(load_flow(path)) if f.level == "error"]
    assert errors == []


def _item(title="Laptop won't boot", item_id=41):
    return {"ID": item_id, "Title": title, "Author": {"Email": "alex.demo@contoso.com"}}


def test_acknowledge_uses_the_environment_label_from_the_environment():
    sent = []
    mocks = {"Send_acknowledgement": lambda i: sent.append(i["parameters"]) or {"status": "Succeeded", "body": {}}}
    flow = load_flow(ACK)
    for label in ("TEST", "PROD"):
        r = run_flow(flow, _item(), mocks, now=NOW, parameters={"Environment label (cts_EnvironmentLabel)": label,
                                                                "Service desk mailbox (cts_ServiceDeskMailbox)": "sd@contoso.com"})
        assert r.status == "Succeeded"
    assert [s["emailMessage/Subject"] for s in sent] == ["IT request #41 received [TEST]",
                                                         "IT request #41 received [PROD]"]
    assert sent[0]["emailMessage/Cc"] == "sd@contoso.com"
    assert sent[0]["emailMessage/To"] == "alex.demo@contoso.com"


def test_acknowledge_ignores_test_items():
    r = run_flow(load_flow(ACK), _item("[TEST] please ignore"), {}, now=NOW)
    assert r.status == "Skipped"


def test_stale_summary_filters_with_the_cutoff_from_the_variable():
    seen = {}

    def get_items(inputs):
        seen.update(inputs["parameters"])
        return {"status": "Succeeded", "body": {"value": [{"ID": 1}, {"ID": 2}]}}

    mail = []
    mocks = {"Get_stale_requests": get_items,
             "Send_stale_summary": lambda i: mail.append(i["parameters"]["emailMessage/Subject"]) or {"status": "Succeeded", "body": {}}}
    r = run_flow(load_flow(STALE), None, mocks, now=NOW, parameters={"Stale after days (cts_StaleDays)": "7"})
    assert r.status == "Succeeded"
    assert seen["$filter"] == "Status eq 'Triaged' and Modified lt '2026-11-16T09:00:00Z'"
    assert mail == ["2 triaged IT requests are stale"]
