"""What fires the Dataverse trigger (Learn semantics), and the checks on trigger settings."""
import copy

import pytest

from d365kit import evaluate_filter, fires, lint_flow, trigger_settings
from flowkit.lint import lint

from conftest import DIGEST, WON, load_flow, sample


@pytest.fixture
def won_trigger():
    (s,) = trigger_settings(load_flow(WON))
    return s


def test_settings_are_read_from_the_flow(won_trigger):
    assert won_trigger["table"] == "opportunity"
    assert won_trigger["columns"] == ["statecode"]
    assert won_trigger["filter"] == "statecode eq 1"


@pytest.mark.parametrize("prefix", [WON, DIGEST])
def test_both_flows_pass_both_linters(prefix):
    flow = load_flow(prefix)
    assert [str(f) for f in lint(flow)] == []
    assert [str(f) for f in lint_flow(flow)] == []


def test_closing_as_won_fires(won_trigger):
    assert fires(won_trigger, sample("opportunity-won.json"), ["statecode", "statuscode"])


def test_editing_a_won_opportunity_does_not_fire_because_statecode_is_not_in_the_request(won_trigger):
    # Learn: the flow runs only when a Select columns column is included in the update request
    assert not fires(won_trigger, sample("opportunity-won.json"), ["description"])


def test_reopening_does_not_pass_the_filter(won_trigger):
    # statecode is in the request, but the row is open again: the filter expression is false after the save
    assert not fires(won_trigger, sample("opportunity-open.json"), ["statecode"])


def test_an_unchanged_value_in_the_request_still_fires(won_trigger):
    # Learn: the flow runs even when the values included are the same as existing values
    assert fires(won_trigger, sample("opportunity-won.json"), ["statecode"])


def test_without_select_columns_every_update_of_a_won_opportunity_fires(won_trigger):
    loose = dict(won_trigger, columns=[])
    assert fires(loose, sample("opportunity-won.json"), ["description"])


def mutate(prefix, **params):
    flow = copy.deepcopy(load_flow(prefix))
    trig = next(iter(flow["properties"]["definition"]["triggers"].values()))
    for k, v in params.items():
        trig["inputs"]["parameters"][f"subscriptionRequest/{k}"] = v
    return flow


def test_lookup_in_select_columns_is_an_error():
    found = lint_flow(mutate(WON, filteringattributes="statecode,parentaccountid"))
    assert any(f.code == "D365001" and "parentaccountid" in f.message for f in found)
    found = lint_flow(mutate(WON, filteringattributes="_ownerid_value"))
    assert any(f.code == "D365001" for f in found)


def test_primary_key_in_select_columns_is_an_error():
    assert any(f.code == "D365003" for f in lint_flow(mutate(WON, filteringattributes="statecode,opportunityid")))


def test_update_trigger_without_select_columns_is_a_warning():
    found = lint_flow(mutate(WON, filteringattributes=""))
    assert any(f.code == "D365002" and f.level == "warning" for f in found)


def test_filter_text_problems_are_reported_with_the_trigger_name():
    found = lint_flow(mutate(WON, filterexpression="$filter=statecode eq 1"))
    assert any(f.code == "ODATA001" and "When_an_opportunity_is_won" in f.message for f in found)


def test_a_flow_that_updates_its_own_trigger_column_is_warned():
    flow = copy.deepcopy(load_flow(WON))
    acts = flow["properties"]["definition"]["actions"]
    acts["Reopen"] = {"type": "OpenApiConnection", "runAfter": {"Get_opportunity": ["Succeeded"]}, "inputs": {
        "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps",
                 "connectionName": "shared_commondataserviceforapps", "operationId": "UpdateOnlyRecord"},
        "parameters": {"entityName": "opportunities", "recordId": "x", "item/statecode": 0}}}
    assert any(f.code == "D365005" for f in lint_flow(flow))


def test_writing_other_columns_of_the_same_table_is_fine_with_select_columns():
    flow = copy.deepcopy(load_flow(WON))
    flow["properties"]["definition"]["actions"]["Note"] = {
        "type": "OpenApiConnection", "runAfter": {"Get_opportunity": ["Succeeded"]}, "inputs": {
            "host": {"apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps",
                     "connectionName": "shared_commondataserviceforapps", "operationId": "UpdateOnlyRecord"},
            "parameters": {"entityName": "opportunities", "recordId": "x", "item/description": "followed up"}}}
    assert not any(f.code == "D365005" for f in lint_flow(flow))


@pytest.mark.parametrize("bad", ["/opportunities(00000000-0000-0000-0000-0000000000b1)", "00000000-0000-0000-0000-0000000000b1"])
def test_lookup_without_entity_set_name_is_an_error(bad):
    flow = copy.deepcopy(load_flow(WON))
    create = flow["properties"]["definition"]["actions"]["Already_has_kickoff_task"]["actions"]["Create_kickoff_task"]
    create["inputs"]["parameters"]["item/regardingobjectid_opportunity@odata.bind"] = bad
    assert any(f.code == "D365006" for f in lint_flow(flow))


def test_the_trigger_filter_is_valid_odata_for_our_evaluator(won_trigger):
    assert evaluate_filter(won_trigger["filter"], sample("opportunity-won.json"))
