"""ext_audit.py: JSONC parsing, the audit itself, and the CLI against a fake `code` on PATH."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parent.parent
TEAM = EPISODE / "src" / "team-setup"
sys.path.insert(0, str(TEAM / "tools"))

from ext_audit import audit, load_recommendations, parse_installed, strip_jsonc  # noqa: E402

LISTING = textwrap.dedent("""\
    EditorConfig.EditorConfig@0.17.4
    dbaeumer.vscode-eslint@3.0.16
    esbenp.prettier-vscode@11.0.0
    ms-python.python@2026.1.0
    ms-vscode.vscode-typescript-tslint-plugin@1.3.3
""")


# ---- JSONC -------------------------------------------------------------------------------------

def test_the_real_workspace_file_is_jsonc_and_plain_json_fails():
    text = (TEAM / ".vscode" / "extensions.json").read_text()
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)                               # what most scripts do first
    data = json.loads(strip_jsonc(text))
    assert "ms-python.python" in data["recommendations"]


def test_strip_jsonc_keeps_slashes_inside_strings():
    text = '{ "url": "https://contoso.com/a//b", /* block */ "x": "/* not a comment */", // tail\n "y": [1,2,], }'
    assert json.loads(strip_jsonc(text)) == {"url": "https://contoso.com/a//b", "x": "/* not a comment */", "y": [1, 2]}


def test_strip_jsonc_handles_escaped_quotes():
    assert json.loads(strip_jsonc(r'{"a": "say \"hi\" // still text"} // gone')) == {"a": 'say "hi" // still text'}


def test_settings_json_is_valid_jsonc_and_matches_hook_length():
    settings = json.loads(strip_jsonc((TEAM / ".vscode" / "settings.json").read_text()))
    assert settings["git.inputValidation"] is True
    assert settings["git.inputValidationSubjectLength"] == 72      # same limit as the episode 1 hook
    formatters = {v["editor.defaultFormatter"] for k, v in settings.items() if k.startswith("[")}
    rec, _ = load_recommendations(TEAM / ".vscode" / "extensions.json")
    assert formatters <= set(rec), "every default formatter must be a recommended extension"


def test_invalid_ids_are_rejected(tmp_path):
    f = tmp_path / "extensions.json"
    f.write_text('{"recommendations": ["prettier"]}')
    with pytest.raises(ValueError, match="publisher.name"):
        load_recommendations(f)


# ---- audit -------------------------------------------------------------------------------------

def test_parse_installed_lowercases_ids_and_skips_noise():
    installed = parse_installed("Extensions installed on WSL: Ubuntu:\n" + LISTING + "\n")
    assert installed["editorconfig.editorconfig"] == "0.17.4"
    assert len(installed) == 5


def test_audit_is_case_insensitive_and_reports_missing_and_unwanted():
    rec, unwanted = load_recommendations(TEAM / ".vscode" / "extensions.json")
    report = audit(rec, unwanted, parse_installed(LISTING))
    assert report.missing == ["ms-dotnettools.csdevkit", "ms-azuretools.vscode-bicep", "github.vscode-github-actions"]
    assert report.unwanted_installed == ["ms-vscode.vscode-typescript-tslint-plugin"]
    assert "editorconfig.editorconfig@0.17.4" in report.ok
    assert not report.clean


def test_audit_clean_machine():
    report = audit(["a.b", "c.d"], ["x.y"], {"a.b": "1.0.0", "c.d": "2.0.0"})
    assert report.clean and report.ok == ["a.b@1.0.0", "c.d@2.0.0"]


# ---- CLI with a fake `code` --------------------------------------------------------------------

FAKE_CODE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    state = os.environ["FAKE_CODE_STATE"]
    args = sys.argv[1:]
    with open(os.environ["FAKE_CODE_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    if args == ["--list-extensions", "--show-versions"]:
        print(open(state).read(), end="")
    elif args and args[0] == "--install-extension":
        ids = args[1::2]
        with open(state, "a") as f:
            for i in ids:
                f.write(f"{i}@1.0.0\\n")
        for i in ids:
            print(f"Extension '{i}' v1.0.0 was successfully installed.")
    else:
        sys.exit(f"unexpected args {args}")
""")


@pytest.fixture
def cli(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "code").write_text(FAKE_CODE)
    (bindir / "code").chmod(0o755)
    state, log = tmp_path / "state.txt", tmp_path / "log.txt"
    state.write_text(LISTING)

    def run(*args):
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "FAKE_CODE_STATE": str(state), "FAKE_CODE_LOG": str(log)}
        r = subprocess.run([sys.executable, str(TEAM / "tools" / "ext_audit.py"), "--workspace", str(TEAM), *args],
                           capture_output=True, text=True, env=env)
        calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        return r, calls

    return run


def test_cli_report_exits_1_when_not_clean(cli):
    r, calls = cli()
    assert r.returncode == 1
    assert "MISSING   ms-dotnettools.csdevkit" in r.stdout
    assert "UNWANTED  ms-vscode.vscode-typescript-tslint-plugin" in r.stdout
    assert r.stdout.strip().endswith("4/7 recommended installed, 3 missing, 1 unwanted")
    assert calls == [["--list-extensions", "--show-versions"]]


def test_cli_install_uses_one_call_with_repeated_flags(cli):
    r, calls = cli("--install", "--json")
    assert calls[1] == ["--install-extension", "ms-dotnettools.csdevkit",
                        "--install-extension", "ms-azuretools.vscode-bicep",
                        "--install-extension", "github.vscode-github-actions"]
    report = json.loads(r.stdout[r.stdout.index("{"):])
    assert report["missing"] == []
    assert report["unwanted_installed"] == ["ms-vscode.vscode-typescript-tslint-plugin"]   # never uninstalled
    assert r.returncode == 1


def test_cli_installed_file_needs_no_code_cli(cli, tmp_path):
    saved = tmp_path / "saved.txt"
    saved.write_text("\n".join(f"{e}@1.0.0" for e in [
        "editorconfig.editorconfig", "dbaeumer.vscode-eslint", "esbenp.prettier-vscode", "ms-python.python",
        "ms-dotnettools.csdevkit", "ms-azuretools.vscode-bicep", "github.vscode-github-actions"]))
    r, calls = cli("--installed-file", str(saved))
    assert r.returncode == 0 and calls == []
    assert "7/7 recommended installed, 0 missing, 0 unwanted" in r.stdout


def test_cli_explains_when_code_is_not_on_path(tmp_path):
    r = subprocess.run([sys.executable, str(TEAM / "tools" / "ext_audit.py"), "--workspace", str(TEAM)],
                       capture_output=True, text=True, env={"PATH": "/nonexistent"})
    assert r.returncode != 0 and "Shell Command: Install 'code' command in PATH" in r.stderr
