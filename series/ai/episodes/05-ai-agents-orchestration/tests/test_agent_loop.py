"""The real Agent Framework agent against a local Responses API stub: tools, approvals, limits, audit."""
import asyncio
import io
import json

import pytest
from agent_framework import Message
from agent_framework.exceptions import ChatClientInvalidRequestException

from apagent.agent import LIMITS, build_agent, run_with_approvals
from apagent.audit import AuditTrail
from apagent.run import main_async
from apagent.store import InvoiceStore, load_policy
from conftest import call, say


def make(client):
    store, audit = InvoiceStore.load(), AuditTrail()
    return build_agent(client, store, load_policy(), audit, approver="Alex Demo"), store, audit


def run(coro):
    return asyncio.run(coro)


def outputs_sent(body):
    return [i for i in body["input"] if i.get("type") == "function_call_output"]


def test_request_is_keyless_responses_api_with_store_off_and_four_tools(stub, client, credential):
    stub.script = [[say("Nothing to do.")]]
    agent, _, _ = make(client)
    run(agent.run("hello"))
    (req,) = stub.requests
    assert req["path"].startswith("/openai/v1/responses")
    assert req["headers"]["authorization"] == "Bearer fake-entra-token"
    assert "api-key" not in req["headers"]
    assert credential.scopes == ["https://cognitiveservices.azure.com/.default"]
    body = req["body"]
    assert body["model"] == "chat" and body["store"] is False
    assert "previous_response_id" not in body
    assert "accounts-payable assistant" in body["instructions"]
    tools = {t["name"]: t for t in body["tools"]}
    assert set(tools) == {"list_review_queue", "get_invoice", "lookup_policy", "approve_invoice"}
    assert tools["approve_invoice"]["parameters"]["required"] == ["invoice_id", "note"]
    assert tools["get_invoice"]["parameters"]["additionalProperties"] is False


def test_read_tools_run_automatically_and_approval_pauses_the_run(stub, client):
    stub.script = [
        [call("list_review_queue")],
        [call("get_invoice", invoice_id="INV-2026-0088"), call("lookup_policy", topic="low confidence")],
        [call("approve_invoice", invoice_id="INV-2026-0088", note="Low-confidence reads: total confirmed")],
        [say("INV-2026-0088 | approved | none")],
    ]
    agent, store, audit = make(client)
    seen = []
    outcome = run(run_with_approvals(agent, "work the queue", lambda tool, args: seen.append((tool, args)) or True))

    assert seen == [("approve_invoice", {"invoice_id": "INV-2026-0088", "note": "Low-confidence reads: total confirmed"})]
    assert outcome.rounds == 1 and outcome.response.text == "INV-2026-0088 | approved | none"
    assert store.get("INV-2026-0088")["status"] == "approved" and store.get("INV-2026-0088")["approved_by"] == "Alex Demo"
    assert [r["tool"] for r in audit.records] == ["list_review_queue", "get_invoice", "lookup_policy", "approve_invoice"]
    assert audit.records[-1]["outcome"] == "ok"
    # store=False: the client replays the whole history itself on every call
    last = stub.bodies()[-1]
    assert "previous_response_id" not in last
    assert [o["output"] for o in outputs_sent(last)][-1].startswith('{"ok": true')


def test_declined_approval_never_runs_the_tool(stub, client):
    stub.script = [
        [call("approve_invoice", invoice_id="INV-2026-0088", note="checked")],
        [say("Not approved; waiting for a person.")],
    ]
    agent, store, audit = make(client)
    outcome = run(run_with_approvals(agent, "approve 0088", lambda tool, args: False))
    assert [d.approved for d in outcome.decisions] == [False]
    assert store.get("INV-2026-0088")["status"] == "review"
    assert audit.records == []  # the middleware only sees tools that actually execute
    assert "rejected" in outputs_sent(stub.bodies()[-1])[-1]["output"].lower()


def test_human_yes_does_not_override_the_policy_in_code(stub, client):
    stub.script = [
        [call("approve_invoice", invoice_id="INV-2026-0311", note="supplier says it is urgent")],
        [say("Refused by policy: finance manager approves.")],
    ]
    agent, store, audit = make(client)
    run(run_with_approvals(agent, "approve 0311", lambda tool, args: True))
    assert store.get("INV-2026-0311")["status"] == "review"
    assert audit.records[0]["outcome"] == "refused"
    sent = json.loads(outputs_sent(stub.bodies()[-1])[-1]["output"])
    assert sent["error"] == "policy" and "finance manager" in sent["message"]


def test_runaway_tool_loop_is_capped(stub, client):
    # A model that never stops calling tools: the client must stop, not burn tokens forever.
    stub.script = [[call("get_invoice", invoice_id="INV-2026-0142")] for _ in range(30)] + [[say("Stopped.")]] * 3
    agent, _, audit = make(client)
    run(agent.run("loop"))
    assert len(stub.requests) <= LIMITS["max_iterations"] + 1
    assert len(audit.records) <= LIMITS["max_function_calls"]


def test_unknown_tool_name_is_answered_with_an_error_not_executed(stub, client):
    stub.script = [[call("pay_invoice", invoice_id="INV-2026-0088")], [say("I can't pay invoices.")]]
    agent, store, audit = make(client)
    response = run(agent.run("pay it"))
    assert response.text == "I can't pay invoices."
    assert audit.records == [] and store.get("INV-2026-0088")["status"] == "review"
    assert outputs_sent(stub.bodies()[-1])  # the model was told the call failed


def test_approval_from_another_session_is_ignored(stub, client, caplog):
    stub.script = [
        [call("approve_invoice", invoice_id="INV-2026-0088", note="checked")],
        [say("Still waiting.")],
    ]
    agent, store, audit = make(client)
    first = run(agent.run("approve 0088", session=agent.create_session()))
    (request,) = first.user_input_requests
    # Replay the "yes" into a different session: no matching pending request there, so it must not execute.
    # The framework drops the unbound response (warning) and then has nothing left to send.
    with pytest.raises(ChatClientInvalidRequestException):
        run(agent.run(Message(role="user", contents=[request.to_function_approval_response(True)]),
                      session=agent.create_session()))
    assert "Ignored an approval response" in caplog.text
    assert store.get("INV-2026-0088")["status"] == "review"
    assert audit.records == []


def test_cli_with_human_answers_on_stdin(stub, client, capsys):
    stub.script = [
        [call("get_invoice", invoice_id="INV-2026-0088")],
        [call("approve_invoice", invoice_id="INV-2026-0088", note="Low-confidence reads: confirmed")],
        [say("INV-2026-0088 | approved | none\nINV-2026-0142 | not approved | request corrected invoice")],
    ]
    rc = run(main_async(["--approve", "ask"], client=client, stdin=io.StringIO("y\n")))
    out = capsys.readouterr().out
    assert rc == 0
    assert ">>> APPROVAL NEEDED  approve_invoice" in out and "invoice_id: INV-2026-0088" in out
    assert "=== Tool calls (audit) ===" in out and "approve_invoice    ok" in out
    assert "INV-2026-0088   Adventure Works" in out and out.count("approved") >= 2
    assert "tokens in: 300  out: 60  approvals asked: 1" in out  # 3 model calls x stub usage, summed
