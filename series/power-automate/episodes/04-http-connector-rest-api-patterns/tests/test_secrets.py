"""The client secret is read at run time and never appears in the run history."""
import json

from flowkit.sim import SECURED

from conftest import page_calls


def test_secret_is_hidden_in_run_history(flow, harness, graph):
    r = harness.run(flow)
    assert r.actions["Get_client_secret"].outputs == SECURED       # Secure outputs on the Dataverse action
    assert all(c.inputs == SECURED for c in page_calls(r))          # Secure inputs on the HTTP action
    everything = json.dumps([(n, res.inputs, res.outputs) for n, res in r.history], default=str)
    assert graph.state.client_secret not in everything


def test_without_secure_inputs_the_secret_would_be_visible(flow, harness, graph):
    del flow["properties"]["definition"]["actions"]["Get_all_pages"]["actions"]["Get_users_page"]["runtimeConfiguration"]
    r = harness.run(flow)
    visible = json.dumps(page_calls(r)[0].inputs)
    assert graph.state.client_secret in visible


def test_the_definition_contains_no_credential(flow):
    text = json.dumps(flow)
    assert "lab-secret-not-real" not in text
    auth = flow["properties"]["definition"]["actions"]["Get_all_pages"]["actions"]["Get_users_page"]["inputs"]["authentication"]
    assert auth["type"] == "ActiveDirectoryOAuth"
    assert auth["secret"] == "@body('Get_client_secret')?['EnvironmentVariableSecretValue']"
