import json
import subprocess
import sys

from copilot_flow_review.cli import main
from conftest import ROOT

SAMPLES = ROOT / "src" / "samples"


def run(*args):
    return main(list(args))


def test_flow_command_exit_codes_and_output(capsys):
    assert run("flow", str(SAMPLES / "loan-reminders-draft.json")) == 0   # warnings only
    out = capsys.readouterr().out
    assert "FR001" in out and "0 errors, 4 warnings, 1 notes" in out


def test_expr_error_gives_exit_1(capsys):
    assert run("expr", "concat(variables('Phone')") == 1
    assert "EX001" in capsys.readouterr().out


def test_prompt_command_json(capsys):
    assert run("prompt", "Fix my flow", "--mode", "edit", "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert {d["code"] for d in data} >= {"PL005"}


def test_clean_prompt_exit_0(capsys):
    assert run("prompt", "When an email arrives in Outlook, post the subject in the Teams General channel") == 0
    assert capsys.readouterr().out.startswith("OK")


def test_missing_file_is_a_usage_error(capsys):
    assert run("flow", str(SAMPLES / "nope.json")) == 2
    assert "error:" in capsys.readouterr().err


def test_runs_as_a_module():
    r = subprocess.run([sys.executable, "-m", "copilot_flow_review", "expr", "concat('a','b')"],
                       cwd=ROOT / "src", capture_output=True, text=True)
    assert r.returncode == 0
    assert "nothing found" in r.stdout


def test_flow_folder_reviews_every_flow_and_skips_other_files(tmp_path, capsys):
    import shutil
    wf = tmp_path / "Workflows"
    wf.mkdir()
    shutil.copy(SAMPLES / "loan-reminders-draft.json", wf / "Draft-00000000-0000-0000-0000-000000000001.json")
    shutil.copy(SAMPLES / "loan-reminders-reviewed.json", wf / "Reviewed-00000000-0000-0000-0000-000000000002.json")
    (wf / "Draft-00000000-0000-0000-0000-000000000001.json.data.xml").write_text("<x/>")
    (tmp_path / "other.json").write_text('{"hello": "world"}')
    assert run("flow", str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert out.count("0 errors") == 2
    assert "other.json" not in out


def test_flow_folder_without_flows_is_a_usage_error(tmp_path, capsys):
    (tmp_path / "x.json").write_text("{}")
    assert run("flow", str(tmp_path)) == 2
    assert "No flow definitions" in capsys.readouterr().err
