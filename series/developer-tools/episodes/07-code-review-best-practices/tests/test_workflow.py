"""pr-review-kit.yml read the way GitHub reads it, plus the jobs' own commands run for real on a real branch."""
from __future__ import annotations

import json
import re
import subprocess
import sys

import jsonschema
import yaml

from conftest import APP, FIXTURES, TESTS, WORKFLOW, commit, git, load_json, load_workflow, needs_git, new_repo, write

WF = load_workflow()
JOBS = WF["jobs"]
PINS = {k: v for k, v in load_json(FIXTURES / "actions" / "pins.json").items() if not k.startswith("_")}
CHECKOUT = yaml.safe_load((FIXTURES / "actions" / "actions_checkout.yml").read_text())


def test_matches_the_github_workflow_schema():
    jsonschema.validate(WF, json.loads((TESTS / "schemas" / "github-workflow.json").read_text()))


def test_job_names_equal_ids_so_required_checks_stay_stable():
    assert {j: v["name"] for j, v in JOBS.items()} == {j: j for j in JOBS} == {
        "pr-size": "pr-size", "pr-description": "pr-description", "review-routing": "review-routing"}
    assert all(v["timeout-minutes"] <= 10 for v in JOBS.values())


def test_edited_is_a_trigger_or_a_fixed_description_is_never_rechecked():
    # GitHub docs: by default pull_request runs only for opened, synchronize and reopened.
    types = WF["on"]["pull_request"]["types"]
    assert {"opened", "edited", "synchronize", "reopened"} <= set(types)


def test_read_only_token_and_cancelled_when_outdated():
    assert WF["permissions"] == {"contents": "read"}
    assert WF["concurrency"]["cancel-in-progress"] is True


def test_checkout_is_pinned_and_every_input_exists():
    for job in JOBS.values():
        co = job["steps"][0]
        action, _, sha = co["uses"].partition("@")
        assert action == "actions/checkout" and sha == PINS[action]["sha"] and re.fullmatch(r"[0-9a-f]{40}", sha)
        assert f"# {PINS[action]['tag']}" in WORKFLOW.read_text()
        assert set(co.get("with", {})) <= set(CHECKOUT["inputs"])


def test_jobs_that_diff_fetch_the_whole_history_and_the_description_job_does_not_need_to():
    assert JOBS["pr-size"]["steps"][0]["with"] == {"fetch-depth": 0}
    assert JOBS["review-routing"]["steps"][0]["with"] == {"fetch-depth": 0}
    assert "with" not in JOBS["pr-description"]["steps"][0]


def test_pull_request_text_reaches_the_shell_only_through_env():
    for job in JOBS.values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), step
    body = JOBS["pr-description"]["steps"][1]
    assert body["env"] == {"PR_BODY": "${{ github.event.pull_request.body }}"}
    assert body["run"] == "printf '%s' \"$PR_BODY\" | python3 tools/review_kit/cli.py description -"
    for name in ("pr-size", "review-routing"):
        env = JOBS[name]["steps"][1]["env"]
        assert env == {"BASE_SHA": "${{ github.event.pull_request.base.sha }}", "HEAD_SHA": "${{ github.event.pull_request.head.sha }}"}


def test_the_commands_name_files_that_exist_and_flags_the_cli_accepts():
    assert (APP / "tools" / "review_kit" / "cli.py").is_file()
    runs = [s["run"] for j in JOBS.values() for s in j["steps"] if "run" in s]
    for r in runs:
        for part in re.findall(r"tools/[\w/]+\.py", r):
            assert (APP / part).is_file()
    help_text = subprocess.run([sys.executable, str(APP / "tools/review_kit/cli.py"), "size", "--help"], capture_output=True, text=True).stdout
    assert "--fail-above" in help_text


@needs_git
def test_the_three_jobs_commands_on_a_real_pull_request_branch(tmp_path):
    """Run each job's `run:` line with the env GitHub would provide, in a clone that has the app's files."""
    repo = new_repo(tmp_path / "r")
    write(repo, {".github/CODEOWNERS": (APP / ".github/CODEOWNERS").read_text(), "tools/review_kit/.keep": ""})
    # the real tool, copied into the repo like in the throwaway demo repository
    import shutil
    shutil.copytree(APP / "tools" / "review_kit", repo / "tools" / "review_kit", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    base = commit(repo, "chore: add the kit")
    git(repo, "switch", "-q", "-c", "feature")
    head = commit(repo, "feat: a change", {"src/Contoso.Orders.Api/Program.cs": "x\n" * 20, "tests/T.cs": "y\n" * 5})
    body = (APP.parent / "review-demo" / "pr-body.good.md").read_text()
    env = {"BASE_SHA": base, "HEAD_SHA": head, "PR_BODY": body, "GITHUB_STEP_SUMMARY": str(tmp_path / "sum.md")}
    import os
    for name in JOBS:
        run = JOBS[name]["steps"][1]["run"]
        res = subprocess.run(["bash", "-c", run], cwd=repo, env={**os.environ, **env}, capture_output=True, text=True)
        assert res.returncode == 0, f"{name}: {res.stdout}{res.stderr}"
    summary = (tmp_path / "sum.md").read_text()
    assert "size/S: 25 changed lines" in summary and "@contoso/orders-team" in summary
    # and the description job fails when the body is empty (a PR opened with no description has body null -> "")
    res = subprocess.run(["bash", "-c", JOBS["pr-description"]["steps"][1]["run"]], cwd=repo,
                         env={**os.environ, **env, "PR_BODY": ""}, capture_output=True, text=True)
    assert res.returncode == 1
