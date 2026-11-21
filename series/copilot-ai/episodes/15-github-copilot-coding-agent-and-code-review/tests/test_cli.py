import json

from agent_ready.cli import main


def test_setup_steps_ok(demo, capsys):
    assert main(["setup-steps", str(demo / ".github/workflows/copilot-setup-steps.yml")]) == 0
    assert "OK" in capsys.readouterr().out


def test_issue_bad_returns_1(demo, capsys):
    assert main(["issue", str(demo / "issues/02-vague-make-pricing-better.md")]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_assign_is_a_dry_run_by_default(capsys):
    assert main(["assign", "a/b", "3"]) == 0
    out = capsys.readouterr().out
    assert "copilot-swe-agent[bot]" in out and "dry run" in out


def test_assign_bad_repo_exits_2(capsys):
    assert main(["assign", "nobody", "3"]) == 2


def test_gate_from_files(tmp_path, capsys):
    pr = {"user": {"login": "Copilot"}, "draft": False, "state": "open", "merged": False}
    (tmp_path / "pr.json").write_text(json.dumps(pr))
    (tmp_path / "rv.json").write_text(json.dumps([{"user": {"login": "sam.demo"}, "state": "APPROVED", "submitted_at": "1"}]))
    (tmp_path / "runs.json").write_text(json.dumps({"workflow_runs": [{"name": "ci", "status": "completed", "conclusion": "success"}]}))
    rc = main(["gate", "--requested-by", "alex.demo", "--pr-json", str(tmp_path / "pr.json"), "--reviews-json", str(tmp_path / "rv.json"), "--runs-json", str(tmp_path / "runs.json")])
    assert rc == 0 and "ready for a human to merge" in capsys.readouterr().out
