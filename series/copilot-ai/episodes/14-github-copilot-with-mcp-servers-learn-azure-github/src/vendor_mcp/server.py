"""MCP server: read-only tools over the Contoso vendor list. Transport: stdio (default)."""
from __future__ import annotations

from typing import TypedDict

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from . import data

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "contoso-vendors",
    version="1.0.0",
    instructions="Read-only facts about Contoso's four fictional vendors: renewal dates, costs, notice deadlines.",
)


class VendorInfo(TypedDict):
    name: str
    service: str
    owner: str
    annual_cost_eur: int
    renewal_date: str
    days_to_renewal: int
    notice_deadline: str
    notice_deadline_passed: bool


class CostSummary(TypedDict):
    vendors: int
    total_eur: int


@mcp.tool(annotations=READ_ONLY)
def list_renewals(within_days: int = 90, today: str | None = None) -> list[VendorInfo]:
    """Vendors renewing within N days (soonest first), with notice deadline and whether it has passed.

    today: optional ISO date (YYYY-MM-DD); defaults to the current date.
    """
    try:
        return data.list_renewals(data.load(), within_days, data.parse_today(today))
    except data.VendorError as exc:
        raise ToolError(str(exc)) from exc  # a failure the caller can fix: the message reaches the model


@mcp.tool(annotations=READ_ONLY)
def get_vendor(name: str, today: str | None = None) -> VendorInfo:
    """One vendor by (part of) its name: owner, cost, renewal date and notice deadline."""
    try:
        return data.find_vendor(data.load(), name, data.parse_today(today))
    except data.VendorError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations=READ_ONLY)
def total_cost(within_days: int = 365, today: str | None = None) -> CostSummary:
    """Total yearly cost in whole euros of the vendors renewing within N days."""
    try:
        rows = data.list_renewals(data.load(), within_days, data.parse_today(today))
    except data.VendorError as exc:
        raise ToolError(str(exc)) from exc
    return {"vendors": len(rows), "total_eur": sum(r["annual_cost_eur"] for r in rows)}


def main() -> None:
    mcp.run("stdio")
