"""Sequential workflow checker -> writer with the real orchestrations package against the stub."""
import asyncio

from apagent.pipeline import check_and_draft, main_async, save_draft
from apagent.store import InvoiceStore, load_policy
from conftest import call, say

FINDINGS = ("INVOICE: INV-2026-0142 from Northwind Catering, total 1240.00 EUR\n"
            "ISSUE: subtotal 1000.00 + tax 230.00 = 1230.00, not 1240.00\n"
            "POLICY: Arithmetic mismatches - never approved, ask for a corrected invoice\n"
            "ACTION: send a corrected invoice")
DRAFT = "Subject: Corrected invoice needed for INV-2026-0142\n\nDear Northwind Catering, ...\nContoso Accounts Payable"


def script():
    return [
        [call("get_invoice", invoice_id="INV-2026-0142"), call("lookup_policy", topic="arithmetic mismatch")],
        [say(FINDINGS)],
        [say(DRAFT)],
    ]


def test_checker_then_writer_least_privilege(stub, client):
    stub.script = script()
    result = asyncio.run(check_and_draft(client, "INV-2026-0142", InvoiceStore.load(), load_policy()))
    assert result == {"invoice_id": "INV-2026-0142", "findings": FINDINGS, "draft": DRAFT}

    checker_first, checker_second, writer = stub.bodies()
    assert {t["name"] for t in checker_first["tools"]} == {"get_invoice", "lookup_policy"}
    assert "approve_invoice" not in str(checker_first["tools"])
    assert "tools" not in writer or not writer["tools"]            # the writer has no tools at all
    assert writer["instructions"].startswith("You draft a short, polite e-mail")
    # context filter: the writer sees the checker's answer only, not the raw tool traffic or the invoice JSON
    types = [i.get("type") for i in writer["input"]]
    assert "function_call" not in types and "function_call_output" not in types
    assert len(writer["input"]) == 1 and writer["input"][0]["role"] == "user"
    text = writer["input"][0]["content"][0]["text"]
    assert text == "Checker findings:\n" + FINDINGS and "vendor_vat" not in str(writer["input"])


def test_chain_only_agent_responses_alone_would_leak_tool_results(stub, client):
    """The gotcha behind findings_only(): the checker's response messages include its tool calls and results."""
    from agent_framework import Agent
    from agent_framework.orchestrations import SequentialBuilder

    from apagent.pipeline import CHECKER, WRITER
    from apagent.tools import build_tools

    stub.script = script()
    tools = build_tools(InvoiceStore.load(), load_policy())
    checker = Agent(client=client, name="checker", instructions=CHECKER, tools=tools.read,
                    default_options={"store": False})
    writer = Agent(client=client, name="writer", instructions=WRITER, default_options={"store": False})
    wf = SequentialBuilder(participants=[checker, writer], chain_only_agent_responses=True).build()
    asyncio.run(wf.run("Check invoice INV-2026-0142."))
    writer_input = stub.bodies()[-1]["input"]
    assert "function_call_output" in [i.get("type") for i in writer_input]
    assert "vendor_vat" in str(writer_input)


def test_findings_only_without_an_answer():
    from agent_framework import Message

    from apagent.pipeline import findings_only

    (m,) = findings_only([Message(role="user", contents=["check it"])])
    assert m.role == "user" and "no e-mail can be drafted" in m.text


def test_cli_saves_a_draft_marked_not_sent(stub, client, tmp_path, capsys):
    stub.script = script()
    rc = asyncio.run(main_async(["INV-2026-0142", "--outbox", str(tmp_path)], client=client))
    out = capsys.readouterr().out
    assert rc == 0 and "=== checker ===" in out and "=== writer ===" in out
    text = (tmp_path / "INV-2026-0142-draft.md").read_text()
    assert text.startswith("<!-- DRAFT - not sent.") and DRAFT in text and FINDINGS in text


def test_save_draft_creates_the_outbox(tmp_path):
    p = save_draft({"invoice_id": "INV-1", "findings": "f", "draft": "d"}, tmp_path / "new" / "outbox")
    assert p.name == "INV-1-draft.md" and p.exists()
