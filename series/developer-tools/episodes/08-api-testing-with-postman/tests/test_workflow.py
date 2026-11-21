"""The workflow, read the way GitHub would read it. No local runner exists for GitHub Actions, so these tests
catch what otherwise fails only after a push: schema errors, unpinned actions, typos in action inputs, scripts and
npm scripts that don't exist, expressions inside `run:`. The commands the workflow calls are run for real in
test_run_script.py."""
from __future__ import annotations

import json
import re

import jsonschema

from conftest import API_TESTS, APP, SCRIPT, TESTS, action_manifest, load_json, load_workflow, pins

WF = load_workflow()
JOB = WF["jobs"]["api-tests"]
STEPS = JOB["steps"]


def uses_steps():
    return [s for s in STEPS if "uses" in s]


def test_matches_the_github_workflow_schema():
    jsonschema.validate(WF, json.loads((TESTS / "schemas" / "github-workflow.json").read_text()))


def test_one_job_whose_name_is_its_id_so_a_required_check_stays_stable():
    assert list(WF["jobs"]) == ["api-tests"] and JOB["name"] == "api-tests"
    assert isinstance(JOB["timeout-minutes"], int) and JOB["timeout-minutes"] <= 20


def test_read_only_token_and_triggers():
    assert WF["permissions"] == {"contents": "read"}
    assert set(WF["on"]) == {"pull_request", "push"} and WF["on"]["push"]["branches"] == ["main"]


def test_every_action_is_pinned_to_the_recorded_commit_with_a_version_comment():
    text = (APP / ".github" / "workflows" / "api-tests.yml").read_text()
    recorded = pins()
    for step in uses_steps():
        action, _, sha = step["uses"].partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", sha), f"{action} is not pinned to a commit"
        assert recorded[action]["sha"] == sha
        assert f"{step['uses']} # {recorded[action]['tag']}" in text
    assert {s["uses"].split("@")[0] for s in uses_steps()} == set(recorded)


def test_every_with_input_exists_and_required_ones_are_set():
    for step in uses_steps():
        action = step["uses"].split("@")[0]
        inputs = action_manifest(action).get("inputs", {})
        given = step.get("with", {})
        assert set(given) <= set(inputs), f"{action}: unknown input {set(given) - set(inputs)}"
        required = {k for k, v in inputs.items() if v.get("required") and "default" not in v}
        assert required <= set(given), f"{action}: missing {required - set(given)}"


def test_no_expression_is_pasted_into_a_shell_command():
    for step in STEPS:
        assert "${{" not in step.get("run", ""), step


def test_the_scripts_and_npm_scripts_it_calls_exist():
    runs = [s["run"] for s in STEPS if "run" in s]
    assert "bash scripts/run-api-tests.sh" in runs      # via bash: no dependency on the executable bit (lost when files are added from Windows)
    assert SCRIPT.is_file()
    npm_scripts = load_json(API_TESTS / "package.json")["scripts"]
    for r in runs:
        if r.startswith("npm run "):
            assert r.removeprefix("npm run ") in npm_scripts
    for s in STEPS:
        if "working-directory" in s:
            assert (APP / s["working-directory"]).is_dir()


def test_lint_and_coverage_run_before_the_collection_is_run():
    names = [s.get("run", s.get("uses")) for s in STEPS]
    assert names.index("npm run lint") < names.index("npm run coverage") < names.index("bash scripts/run-api-tests.sh")


def test_the_run_expects_the_commit_that_was_checked_out():
    run = next(s for s in STEPS if s.get("run") == "bash scripts/run-api-tests.sh")
    assert run["env"] == {"EXPECTED_VERSION": "${{ github.sha }}"}


def test_node_cache_points_at_a_real_lock_file_and_newman_is_pinned_exactly():
    node = next(s for s in uses_steps() if s["uses"].startswith("actions/setup-node"))
    assert (APP / node["with"]["cache-dependency-path"]).is_file()
    pkg = load_json(API_TESTS / "package.json")
    lock = load_json(API_TESTS / "package-lock.json")
    assert pkg["devDependencies"] == {"newman": "6.2.3"}
    assert lock["packages"]["node_modules/newman"]["version"] == "6.2.3"
    assert next(s for s in STEPS if s.get("run", "").startswith("npm ci"))["working-directory"] == "api-tests"


def test_reports_are_uploaded_even_when_a_test_failed_and_the_path_matches_the_script():
    up = next(s for s in uses_steps() if s["uses"].startswith("actions/upload-artifact"))
    assert "!cancelled()" in up["if"]
    assert up["with"]["path"] == "api-tests/results/" and up["with"]["if-no-files-found"] == "error"
    assert 'results="${RESULTS_DIR:-$tests/results}"' in SCRIPT.read_text()


def test_docker_context_and_git_ignore_the_test_project_and_its_reports():
    assert "api-tests/" in (APP / ".dockerignore").read_text().splitlines()
    assert "api-tests/results/" in (APP / ".gitignore").read_text().splitlines()
    assert "node_modules/" in (APP / ".gitignore").read_text().splitlines()
