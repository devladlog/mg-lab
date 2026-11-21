"""Starts the real server as a subprocess and talks MCP to it over stdio, like VS Code does."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

SRC = Path(__file__).resolve().parents[1] / "src"


def params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", "vendor_mcp"], cwd=SRC)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=60))


def test_lists_three_read_only_tools():
    async def go():
        async with Client(params()) as client:
            return (await client.list_tools()).tools

    tools = run(go())
    assert sorted(t.name for t in tools) == ["get_vendor", "list_renewals", "total_cost"]
    assert all(t.annotations and t.annotations.read_only_hint is True for t in tools)
    assert all(t.description for t in tools)


def test_list_renewals_over_stdio():
    async def go():
        async with Client(params()) as client:
            return await client.call_tool("list_renewals", {"within_days": 130, "today": "2027-03-01"})

    result = run(go())
    assert result.is_error is False
    rows = result.structured_content["result"]
    assert [r["name"] for r in rows] == ["Fabrikam Cloud", "Northwind Print"]
    assert rows[0]["notice_deadline"] == "2026-12-31" and rows[0]["notice_deadline_passed"] is True


def test_total_cost_and_get_vendor_over_stdio():
    async def go():
        async with Client(params()) as client:
            total = await client.call_tool("total_cost", {"within_days": 365, "today": "2027-01-01"})
            vendor = await client.call_tool("get_vendor", {"name": "contoso security", "today": "2027-01-01"})
            return total, vendor

    total, vendor = run(go())
    assert total.structured_content == {"vendors": 4, "total_eur": 45000}
    assert vendor.structured_content["owner"] == "Sam Demo"


def test_errors_reach_the_client_as_tool_errors():
    async def go():
        async with Client(params()) as client:
            return (await client.call_tool("get_vendor", {"name": "Litware"}),
                    await client.call_tool("list_renewals", {"today": "not-a-date"}))

    unknown, bad_date = run(go())
    assert unknown.is_error is True and "no vendor matches" in unknown.content[0].text
    assert bad_date.is_error is True and "YYYY-MM-DD" in bad_date.content[0].text


def test_server_command_from_the_committed_config_starts():
    """The `contosoVendors` entry of .mcp.json is launched as written (python -> this interpreter)."""
    entry = json.loads((SRC / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["contosoVendors"]
    assert entry["command"] == "python" and entry["args"] == ["-m", "vendor_mcp"]

    async def go():
        async with Client(StdioServerParameters(command=sys.executable, args=entry["args"], cwd=SRC)) as client:
            return await client.call_tool("total_cost", {"today": "2027-01-01"})

    assert run(go()).structured_content["total_eur"] == 45000


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("MCP_LIVE") != "1", reason="set MCP_LIVE=1 to call the public Microsoft Learn MCP endpoint")
def test_live_learn_mcp_endpoint_lists_documented_tools():
    async def go():
        async with Client("https://learn.microsoft.com/api/mcp") as client:
            return {t.name for t in (await client.list_tools()).tools}

    names = run(go())
    assert {"microsoft_docs_search", "microsoft_docs_fetch", "microsoft_code_sample_search"} <= names
