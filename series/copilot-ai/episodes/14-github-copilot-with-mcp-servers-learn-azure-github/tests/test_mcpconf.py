import copy
import json
from pathlib import Path

import pytest

from mcpconf import cli
from mcpconf.core import EDITOR, NATIVE, check, detect, to_native

SRC = Path(__file__).resolve().parents[1] / "src"
EXAMPLES = SRC / "examples"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def codes(report) -> set[str]:
    return {f.code for f in report.findings}


def test_detect_formats():
    assert detect({"servers": {}}) == EDITOR
    assert detect({"mcpServers": {}}) == NATIVE
    assert detect({"servers": {}, "mcpServers": {}}) is None
    assert detect({}) is None


def test_committed_configs_are_clean():
    for rel in (".vscode/mcp.json", ".mcp.json"):
        report = check(load(SRC / rel))
        assert report.count("error") == 0 and report.count("warn") == 0, [f.line() for f in report.findings]


def test_committed_native_file_is_what_the_converter_produces():
    produced = to_native(load(SRC / ".vscode" / "mcp.json"), add_tools_star=True).doc
    assert produced == load(SRC / ".mcp.json")


def test_learn_sample_gets_the_documented_warnings():
    report = check(load(EXAMPLES / "azure-learn-sample.vscode-mcp.json"))
    assert {"TYPE_MISSING", "UNPINNED_LATEST", "SERVER_NAME", "AZURE_READWRITE"} <= codes(report)
    assert report.count("error") == 0


def test_github_pat_example_is_valid_but_read_write():
    report = check(load(EXAMPLES / "github-pat.vscode-mcp.json"))
    assert report.count("error") == 0 and "GITHUB_READWRITE" in codes(report)


def test_bad_example_findings():
    report = check(load(EXAMPLES / "bad.vscode-mcp.json"))
    assert {"SECRET_LITERAL", "INPUT_UNDECLARED", "INPUT_UNUSED", "INSECURE_URL", "BARE_VARIABLE"} <= codes(report)


def test_github_readonly_header_counts_as_read_only():
    doc = {"servers": {"github": {"type": "http", "url": "https://api.githubcopilot.com/mcp/",
                                  "headers": {"X-MCP-Readonly": "true"}}}}
    assert "GITHUB_READWRITE" not in codes(check(doc))


def test_native_file_rejects_editor_only_things():
    doc = {
        "mcpServers": {
            "a": {"type": "stdio", "command": "x", "envFile": ".env", "sandboxEnabled": True,
                  "env": {"K": "${input:k}", "E": "${env:HOME}"}, "oauth": {"clientId": "c"}},
            "b": {"type": "stdio", "command": "x", "args": ["${command:pick}"]},
        },
        "inputs": [],
    }
    found = codes(check(doc))
    assert {"EDITOR_ONLY", "INPUT_IN_NATIVE", "ENV_SYNTAX", "OAUTH_SHAPE", "COMMAND_IN_NATIVE"} <= found


def test_structure_errors():
    assert "FORMAT" in codes(check({}))
    assert "NO_SERVERS" in codes(check({"servers": {}}))
    report = check({"servers": {"a": {"type": "ftp"}, "b": {"type": "stdio"}, "c": {"type": "http"}}})
    assert {"TYPE_UNKNOWN", "NO_COMMAND", "NO_URL"} <= codes(report)


def test_convert_pat_example_uses_environment_variable_not_a_value():
    result = to_native(load(EXAMPLES / "github-pat.vscode-mcp.json"))
    header = result.doc["mcpServers"]["github"]["headers"]["Authorization"]
    assert header == "Bearer ${GITHUB_MCP_PAT}"
    assert result.env_vars == ["GITHUB_MCP_PAT"]
    assert "inputs" not in result.doc
    assert any("password input" in n for n in result.notes)
    assert check(result.doc).count("error") == 0


def test_convert_translates_env_oauth_and_drops_editor_fields():
    doc = {"servers": {"x": {"type": "stdio", "command": "run", "env": {"A": "${env:HOME}"}, "envFile": ".env",
                             "dev": {"watch": "src/**"}, "sandboxEnabled": True, "sandbox": {}},
                      "y": {"type": "http", "url": "https://example.com/mcp", "oauth": {"clientId": "abc"}},
                      "z": {"command": "node"}},
           "sandbox": {"filesystem": {}}}
    result = to_native(doc)
    servers = result.doc["mcpServers"]
    assert servers["x"] == {"type": "stdio", "command": "run", "env": {"A": "${HOME}"}}
    assert servers["y"] == {"type": "http", "url": "https://example.com/mcp", "oauthClientId": "abc"}
    assert servers["z"]["type"] == "stdio"
    assert check(result.doc).count("error") == 0


def test_convert_skips_command_inputs_and_refuses_literal_secrets():
    doc = {"servers": {"v": {"type": "stdio", "command": "az", "args": ["${command:pick}"]},
                      "ok": {"type": "http", "url": "https://example.com/mcp"}}}
    result = to_native(doc)
    assert result.skipped == ["v"] and list(result.doc["mcpServers"]) == ["ok"]
    with pytest.raises(ValueError, match="refusing to convert"):
        to_native(load(EXAMPLES / "bad.vscode-mcp.json"))
    with pytest.raises(ValueError, match="not an editor-format"):
        to_native({"mcpServers": {}})


def test_convert_does_not_modify_its_input():
    doc = load(EXAMPLES / "github-pat.vscode-mcp.json")
    before = copy.deepcopy(doc)
    to_native(doc)
    assert doc == before


def test_cli_check_and_convert(tmp_path, capsys):
    assert cli.main(["check", str(SRC / ".vscode" / "mcp.json")]) == 0
    assert cli.main(["check", str(EXAMPLES / "bad.vscode-mcp.json")]) == 1
    assert cli.main(["check", str(EXAMPLES / "azure-learn-sample.vscode-mcp.json")]) == 0
    assert cli.main(["check", str(EXAMPLES / "azure-learn-sample.vscode-mcp.json"), "--strict"]) == 1
    out = tmp_path / ".mcp.json"
    assert cli.main(["convert", str(SRC / ".vscode" / "mcp.json"), "--add-tools-star", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == load(SRC / ".mcp.json")
    assert cli.main(["convert", str(EXAMPLES / "bad.vscode-mcp.json")]) == 2
    assert cli.main(["check", str(tmp_path / "missing.json")]) == 2
    capsys.readouterr()
