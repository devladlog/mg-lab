"""Agent Framework function tools bound to one InvoiceStore.

Read tools run freely. The one tool that changes state, approve_invoice, is marked approval_mode="always_require":
the framework stops and hands the call (name + arguments) back to our code; a person decides. Even after a "yes",
InvoiceStore.approve() still applies the policy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated

from agent_framework import FunctionTool, tool

from .store import InvoiceStore, lookup_policy


@dataclass
class ToolSet:
    read: list[FunctionTool]
    write: list[FunctionTool]

    @property
    def all(self) -> list[FunctionTool]:
        return [*self.read, *self.write]


def build_tools(store: InvoiceStore, policy: dict[str, str], *, approver: str = "AP clerk") -> ToolSet:
    @tool(name="list_review_queue", approval_mode="never_require")
    def list_review_queue() -> str:
        """List the invoices waiting in the accounts-payable review queue, with the reasons they need review."""
        return json.dumps(store.queue())

    @tool(name="get_invoice", approval_mode="never_require")
    def get_invoice(invoice_id: Annotated[str, "Invoice id, for example INV-2026-0142"]) -> str:
        """Get one invoice: vendor, VAT number, date, subtotal, tax, total, status and review reasons."""
        inv = store.get(invoice_id)
        return json.dumps(inv if inv else {"error": "not_found", "invoice_id": invoice_id})

    @tool(name="lookup_policy", approval_mode="never_require")
    def lookup_policy_tool(topic: Annotated[str, "What the policy question is about, e.g. 'approval limit'"]) -> str:
        """Look up the Contoso accounts-payable review policy. Returns matching sections with their headings."""
        hits = lookup_policy(policy, topic)
        return json.dumps(hits or {"error": "no_match", "sections": list(policy)})

    @tool(name="approve_invoice", approval_mode="always_require", max_invocations=5)
    def approve_invoice(
        invoice_id: Annotated[str, "Invoice id to approve"],
        note: Annotated[str, "Why the approval is justified, citing the policy section"],
    ) -> str:
        """Approve an invoice for payment. A person must confirm every call; the policy is enforced again here."""
        return json.dumps(store.approve(invoice_id, note, approver))

    return ToolSet(read=[list_review_queue, get_invoice, lookup_policy_tool], write=[approve_invoice])
