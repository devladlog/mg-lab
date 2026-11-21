import json
from pathlib import Path

import pytest

from azmcp_audit import catalog, cli, policy as pol

ROOT = Path(__file__).resolve().parents[1]
SUBSET = ROOT / "src" / "samples" / "azmcp-4.0.0-beta.9-catalog-subset.json"
READER = ROOT / "src" / "policies" / "contoso-ops-reader.json"
WRITER = ROOT / "src" / "policies" / "contoso-dev-writer.json"


@pytest.fixture(scope="module")
def tools():
    return catalog.load_catalog(SUBSET)


def test_catalog_parses_real_shape(tools):
    assert len(tools) == 78
    g = next(t for t in tools if t.command == "group list")
    assert g.name == "group_list" and g.namespace == "group" and g.read_only and not g.destructive


def test_parser_accepts_plain_booleans_and_bare_list():
    text = json.dumps([{"command": "a b c", "metadata": {"readOnly": True, "secret": False}}])
    (t,) = catalog.parse_catalog(text)
    assert t.name == "a_b_c" and t.read_only and not t.secret and not t.destructive


def test_reader_policy_exposes_only_read_only_tools(tools):
    exposed = pol.expected_tools(tools, pol.Policy.load(READER))
    assert exposed and all(t.read_only for t in exposed)
    assert {t.namespace for t in exposed} <= {"group", "subscription", "monitor", "resourcehealth", "advisor", "policy", "role"}
    names = [t.name for t in exposed]
    assert "group_list" in names and "advisor_recommendation_list" in names
    assert names == sorted(names)


def test_read_only_hides_the_writes_of_the_same_namespaces(tools):
    p = pol.Policy.load(READER)
    full = pol.expected_tools(tools, pol.Policy("x", p.namespaces, read_only=False))
    ro = pol.expected_tools(tools, p)
    assert len(full) > len(ro)
    assert [t for t in full if t not in ro and t.read_only] == []   # only non-read-only tools disappear


def test_reader_policy_has_no_findings_and_writer_policy_does(tools):
    assert pol.findings(tools, pol.Policy.load(READER)) == []
    found = pol.findings(tools, pol.Policy.load(WRITER))
    risks = {r for r, _ in found}
    assert "destructive" in risks and "secret" in risks
    assert any(t.namespace == "keyvault" and r == "secret" for r, t in found)


def test_allow_list_silences_only_the_named_risk(tools):
    p = pol.Policy.load(WRITER)
    p.allow = ["secret"]
    assert "secret" not in {r for r, _ in pol.findings(tools, p)}
    assert "destructive" in {r for r, _ in pol.findings(tools, p)}


def test_policy_validation(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"name": "x", "namespaces": []}))
    with pytest.raises(ValueError, match="at least one namespace"):
        pol.Policy.load(f)
    f.write_text(json.dumps({"name": "x", "namespaces": ["group"], "allow": ["everything"]}))
    with pytest.raises(ValueError, match="Unknown risk"):
        pol.Policy.load(f)


def test_unknown_namespace_is_caught(tools):
    assert pol.unknown_namespaces(tools, pol.Policy("x", ["group", "grup"])) == ["grup"]


def test_start_args_and_vscode_config(tools):
    p = pol.Policy.load(READER)
    assert pol.start_args(p)[:4] == ["server", "start", "--mode", "all"]
    assert pol.start_args(p).count("--namespace") == 7 and pol.start_args(p)[-1] == "--read-only"
    cfg = pol.vscode_mcp_json(p)
    (server,) = cfg["servers"].values()
    assert server["command"] == "npx" and server["args"][:2] == ["-y", "@azure/mcp@4.0.0-beta.9"]
    assert "--read-only" in server["args"] and "latest" not in json.dumps(cfg)


def test_namespace_report_counts(tools):
    rows = {r["namespace"]: r for r in pol.namespace_report(tools, pol.Policy.load(READER))}
    assert rows["monitor"]["tools"] == 28 and rows["monitor"]["exposed"] == 21 and rows["monitor"]["destructive"] == 2
    assert rows["group"]["exposed"] == 2


def test_cli_report_and_config(capsys):
    assert cli.main(["report", str(READER), "--catalog", str(SUBSET), "--fail-on-findings"]) == 0
    out = capsys.readouterr().out
    assert "Findings: 0" in out and "monitor" in out
    assert cli.main(["report", str(WRITER), "--catalog", str(SUBSET), "--fail-on-findings"]) == 1
    assert "[RISK:secret]" in capsys.readouterr().out
    assert cli.main(["config", str(READER), "--catalog", str(SUBSET)]) == 0
    assert json.loads(capsys.readouterr().out)["servers"]


def test_cli_rejects_unknown_namespace(tmp_path, capsys):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"name": "x", "namespaces": ["group", "nope"]}))
    assert cli.main(["report", str(f), "--catalog", str(SUBSET)]) == 2
    assert "nope" in capsys.readouterr().out


def test_azmcp_can_be_a_command_with_arguments():
    assert catalog.as_command("azmcp") == ["azmcp"]
    assert catalog.as_command("node /opt/azmcp/node_modules/@azure/mcp/index.js") == ["node", "/opt/azmcp/node_modules/@azure/mcp/index.js"]
