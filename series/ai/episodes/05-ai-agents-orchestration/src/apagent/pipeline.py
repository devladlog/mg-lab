"""Two agents in a sequential workflow: a checker with read-only tools, then a writer with no tools at all.

    PYTHONPATH=src python -m apagent.pipeline INV-2026-0142 --endpoint $AOAI --deployment chat

Least privilege per agent: the writer has no tools, so it cannot approve, read or change anything, and it gets only
the checker's final text. Note: chain_only_agent_responses=True is NOT enough for that - the checker's "response
messages" include its tool calls and tool results (the raw invoice JSON). A custom context filter removes them.
The draft is saved to outbox/ and marked as not sent: sending stays a human action.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from agent_framework import Agent, AgentExecutor, Message
from agent_framework.orchestrations import SequentialBuilder

from .agent import make_client
from .store import DATA, InvoiceStore, load_policy
from .tools import build_tools

CHECKER = """You check one Contoso supplier invoice from the review queue.
Use get_invoice and lookup_policy. Do not guess any value.
Reply with exactly these lines:
INVOICE: <id> from <vendor>, total <total> <currency>
ISSUE: <what is wrong, with the numbers>
POLICY: <policy section heading> - <what it requires>
ACTION: <what the supplier must do>"""

WRITER = """You draft a short, polite e-mail to the supplier, based only on the checker findings you are given.
Plain text, at most 120 words, starting with 'Subject:'. Mention the invoice id, the issue with its numbers and
the action requested. No promises about payment dates. Sign as 'Contoso Accounts Payable'."""


def findings_only(messages: list[Message]) -> list[Message]:
    """Context filter for the writer: the checker's last text answer, nothing else (no tool calls or results)."""
    for m in reversed(messages):
        if m.role == "assistant" and m.text.strip():
            return [Message(role="user", contents=[f"Checker findings:\n{m.text.strip()}"])]
    return [Message(role="user", contents=["Checker findings: none. Say that no e-mail can be drafted."])]


def build_pipeline(client, store: InvoiceStore, policy: dict[str, str]):
    tools = build_tools(store, policy)
    read_only = [t for t in tools.read if t.name in ("get_invoice", "lookup_policy")]
    checker = Agent(client=client, name="checker", instructions=CHECKER, tools=read_only,
                    default_options={"store": False})
    writer = Agent(client=client, name="writer", instructions=WRITER, default_options={"store": False})
    writer_step = AgentExecutor(writer, id="writer", context_mode="custom", context_filter=findings_only)
    workflow = SequentialBuilder(participants=[checker, writer_step], intermediate_output_from=[checker]).build()
    return workflow, checker, writer


async def check_and_draft(client, invoice_id: str, store: InvoiceStore, policy: dict[str, str]) -> dict:
    workflow, _, _ = build_pipeline(client, store, policy)
    result = await workflow.run(f"Check invoice {invoice_id} and draft the supplier e-mail.")
    findings, draft = "", ""
    for event in result:
        if event.type == "intermediate":
            findings = _text(event.data)
        elif event.type == "output":
            draft = _text(event.data)
    return {"invoice_id": invoice_id, "findings": findings.strip(), "draft": draft.strip()}


def _text(data) -> str:
    if hasattr(data, "text"):
        return data.text
    if isinstance(data, list):
        return "\n".join(getattr(m, "text", str(m)) for m in data)
    return str(data)


def save_draft(result: dict, outbox: Path) -> Path:
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{result['invoice_id']}-draft.md"
    path.write_text("<!-- DRAFT - not sent. A person reviews and sends it. -->\n\n"
                    f"## Checker findings\n\n{result['findings']}\n\n## Draft e-mail\n\n{result['draft']}\n",
                    encoding="utf-8")
    return path


async def main_async(argv=None, *, client=None) -> int:
    ap = argparse.ArgumentParser(description="checker -> writer sequential workflow for one invoice")
    ap.add_argument("invoice_id")
    ap.add_argument("--endpoint")
    ap.add_argument("--deployment", default="chat")
    ap.add_argument("--data", default=str(DATA / "invoices.json"))
    ap.add_argument("--outbox", default="outbox")
    a = ap.parse_args(argv)
    if client is None:
        if not a.endpoint:
            ap.error("--endpoint is required")
        client = make_client(a.endpoint, a.deployment)
    result = await check_and_draft(client, a.invoice_id, InvoiceStore.load(a.data), load_policy())
    print("=== checker ===\n" + result["findings"] + "\n\n=== writer ===\n" + result["draft"])
    print(f"\nsaved {save_draft(result, Path(a.outbox))} (draft, not sent)")
    return 0


def main(argv=None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
