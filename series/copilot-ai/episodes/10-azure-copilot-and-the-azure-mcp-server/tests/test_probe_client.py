"""The stdio client against a local stand-in server (test only)."""
import sys
from pathlib import Path

import pytest

from azmcp_audit import probe

FAKE = [sys.executable, str(Path(__file__).with_name("fake_mcp_server.py"))]


def test_handshake_paging_and_notifications_are_ignored():
    with probe.StdioClient(FAKE) as c:
        info = c.initialize()
        assert info["serverInfo"]["name"] == "fake"
        assert [t["name"] for t in c.list_tools()] == ["group_list", "subscription_list"]


def test_call_round_trip_and_error():
    with probe.StdioClient(FAKE) as c:
        c.initialize()
        assert "subscription" in c.call("group_list", {"subscription": "s"})["content"][0]["text"]
        with pytest.raises(probe.McpError, match="boom failed"):
            c.call("boom")


def test_closed_pipe_is_reported():
    with probe.StdioClient([sys.executable, "-c", "pass"]) as c:
        with pytest.raises(probe.McpError, match="closed the pipe"):
            c.initialize()
