"""SharePoint lint rules (Learn: SharePoint connector, Send HTTP request guidance, avoid anti-patterns)."""
import copy

from flowkit import lint

from conftest import actions, folder_block


def messages(flow, level=None):
    return [f.message for f in lint(flow) if level is None or f.level == level]


def test_the_solution_flow_is_clean(flow):
    assert lint(flow) == []


def test_window_tokens_need_the_modified_trigger(flow):
    bad = copy.deepcopy(flow)
    (trigger,) = bad["properties"]["definition"]["triggers"].values()
    trigger["inputs"]["host"]["operationId"] = "GetOnUpdatedItems"      # "When an item is created or modified"
    assert any("only available with the 'When an item or a file is modified'" in m for m in messages(bad, "error"))


def test_get_changes_since_should_be_the_start_token(flow):
    bad = copy.deepcopy(flow)
    actions(bad)["Get_changes"]["inputs"]["parameters"]["since"] = "@triggerBody()?['Modified']"
    assert any("Trigger Window Start Token" in m for m in messages(bad, "warning"))


def test_rest_calls_without_nometadata_are_flagged(flow):
    bad = copy.deepcopy(flow)
    folder_block(bad)["Get_read_role"]["inputs"]["parameters"]["parameters/headers"] = {}
    assert any("odata=nometadata" in m for m in messages(bad, "warning"))


def test_a_check_on_the_written_column_counts_as_a_guard(flow):
    """Mark escalated writes Status. Two things stop it re-triggering: the trigger condition (Status must be
    Approved) and its own condition (Status must not have changed in the window). Remove the trigger
    condition and the linter still sees the second guard, and the loop really doesn't happen."""
    from conftest import Lab
    bad = copy.deepcopy(flow)
    bad["properties"]["definition"]["triggers"]["When_a_purchase_request_is_modified"]["conditions"] = []
    assert not any("infinite trigger loop" in m for m in messages(bad, "warning"))
    lab = Lab(bad)
    lab.approve()
    lab.poller.poll_until_quiet()
    lab.edit(lab.alex, Amount=14200)
    assert lab.poller.poll_until_quiet() == 2            # the escalation, then one quiet run that sees Status changed
    assert lab.fields["Status"] == "Escalated"


def test_every_connector_is_solution_aware(flow):
    refs = flow["properties"]["connectionReferences"]
    assert set(refs) == {"shared_sharepointonline", "shared_office365"}
    assert all(r["connection"]["connectionReferenceLogicalName"].startswith("cts_") for r in refs.values())
