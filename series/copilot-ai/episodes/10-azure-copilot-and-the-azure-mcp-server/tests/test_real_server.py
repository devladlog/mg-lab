"""Integration tests against the REAL Azure MCP Server binary. Skipped unless AZMCP_BIN points at azmcp (or azmcp is on PATH).
Listing tools needs no Azure sign-in. Install per project, outside this folder:  npm install @azure/mcp@4.0.0-beta.9"""
import os
import shutil
from pathlib import Path

import pytest

from azmcp_audit import catalog, cli, policy as pol, probe

AZMCP = os.environ.get("AZMCP_BIN") or shutil.which("azmcp")
pytestmark = pytest.mark.skipif(not AZMCP, reason="azmcp not installed (set AZMCP_BIN)")

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "src" / "policies" / "contoso-ops-reader.json"
WRITER = ROOT / "src" / "policies" / "contoso-dev-writer.json"


@pytest.fixture(scope="module")
def full_catalog():
    return catalog.parse_catalog(catalog.run_tools_list(AZMCP))


def test_server_publishes_exactly_what_the_catalog_predicts_read_only(full_catalog):
    p = pol.Policy.load(READER)
    _, listed = probe.list_server_tools(AZMCP, pol.start_args(p, "all") + ["--disable-proxy-tools"])
    assert sorted(t["name"] for t in listed) == [t.name for t in pol.expected_tools(full_catalog, p)]
    assert all(t["annotations"]["readOnlyHint"] for t in listed)


def test_server_publishes_exactly_what_the_catalog_predicts_with_writes(full_catalog):
    p = pol.Policy.load(WRITER)
    _, listed = probe.list_server_tools(AZMCP, pol.start_args(p, "all") + ["--disable-proxy-tools"])
    assert sorted(t["name"] for t in listed) == [t.name for t in pol.expected_tools(full_catalog, p)]
    assert any(not t["annotations"]["readOnlyHint"] for t in listed)


def test_read_only_shrinks_the_full_server(full_catalog):
    _, all_tools = probe.list_server_tools(AZMCP, ["server", "start", "--mode", "all", "--disable-proxy-tools"])
    _, ro_tools = probe.list_server_tools(AZMCP, ["server", "start", "--mode", "all", "--read-only", "--disable-proxy-tools"])
    assert len(all_tools) == len(full_catalog)
    assert len(ro_tools) == sum(t.read_only for t in full_catalog) < len(all_tools)


def test_single_mode_is_one_tool():
    _, single = probe.list_server_tools(AZMCP, ["server", "start", "--mode", "single"])
    assert [t["name"] for t in single] == ["azure"]


def test_cli_probe_matches(capsys):
    assert cli.main(["probe", str(READER), "--azmcp", AZMCP]) == 0
    out = capsys.readouterr().out
    assert "Match: yes" in out and "same set" in out


def test_namespace_mode_hides_the_write_commands_too(full_catalog):
    p = pol.Policy.load(READER)
    published, commands = probe.namespace_surface(AZMCP, pol.start_args(p, "namespace"))
    assert commands == {t.name for t in pol.expected_tools(full_catalog, p)}
    assert len(published) < len(commands)           # 8 namespace-level tools publish 36 commands
    assert "advisor_recommendation_update" not in commands
    writable = pol.Policy("w", ["advisor"], read_only=False)
    _, with_writes = probe.namespace_surface(AZMCP, pol.start_args(writable, "namespace"))
    assert "advisor_recommendation_update" in with_writes
