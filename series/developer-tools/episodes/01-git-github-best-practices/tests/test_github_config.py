"""GitHub side: the CI workflow, the ruleset JSON and the two gh scripts (run against a fake `gh` on PATH)."""
import json
import re
import subprocess
import textwrap

import pytest
import yaml

from conftest import KIT

WORKFLOW = KIT / ".github" / "workflows" / "ci.yml"
RULESET = KIT / ".github" / "rulesets" / "protect-main.json"


@pytest.fixture(scope="module")
def workflow():
    data = yaml.safe_load(WORKFLOW.read_text())
    # YAML 1.1 gotcha: PyYAML reads the bare key `on` as the boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def test_workflow_triggers_and_least_privilege(workflow):
    assert set(workflow["on"]) == {"pull_request", "push"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is True


def test_every_action_is_pinned_to_a_full_commit_sha(workflow):
    uses = [s["uses"] for job in workflow["jobs"].values() for s in job["steps"] if "uses" in s]
    assert uses, "expected at least one action"
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref


def test_no_untrusted_expression_inside_run_scripts(workflow):
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), step


def test_every_job_has_a_timeout(workflow):
    assert all("timeout-minutes" in job for job in workflow["jobs"].values())


def test_required_checks_match_the_workflow_job_names(workflow):
    ruleset = json.loads(RULESET.read_text())
    checks = next(r for r in ruleset["rules"] if r["type"] == "required_status_checks")
    contexts = {c["context"] for c in checks["parameters"]["required_status_checks"]}
    job_names = {job.get("name", key) for key, job in workflow["jobs"].items()}
    assert contexts == job_names


def test_ruleset_protects_the_default_branch():
    ruleset = json.loads(RULESET.read_text())
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert ruleset["bypass_actors"] == []
    types = {r["type"] for r in ruleset["rules"]}
    assert {"deletion", "non_fast_forward", "pull_request", "required_status_checks"} <= types
    pr = next(r for r in ruleset["rules"] if r["type"] == "pull_request")["parameters"]
    # the five parameters the REST API marks as required for the pull_request rule
    for key in ("dismiss_stale_reviews_on_push", "require_code_owner_review", "require_last_push_approval",
                "required_approving_review_count", "required_review_thread_resolution"):
        assert key in pr
    assert pr["allowed_merge_methods"] == ["squash"]
    assert pr["required_approving_review_count"] >= 1


def test_pr_title_cli_treats_a_hostile_title_as_text():
    title = 'x"; touch /tmp/pwned_by_title; echo "'
    r = subprocess.run(["python3", str(KIT / "tools/repo_guard/cli.py"), "title", title],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "PR title is not a Conventional Commit" in r.stderr
    ok = subprocess.run(["python3", str(KIT / "tools/repo_guard/cli.py"), "title", "feat(api)!: drop v1"],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "BREAKING" in ok.stdout


# ---- fake gh -------------------------------------------------------------------------------------

FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["GH_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
    if "--input" in args:
        json.load(open(args[args.index("--input") + 1]))     # gh would send it: must be valid JSON
    method = args[args.index("--method") + 1] if "--method" in args else "GET"
    if method == "GET":
        existing = os.environ.get("FAKE_RULESET_ID")
        if existing:
            print(existing)                                  # what --jq '.[] | select(...) | .id' prints
    elif method in ("POST", "PUT"):
        verb = "created" if method == "POST" else "updated"
        print(f"{verb} ruleset {os.environ.get('FAKE_RULESET_ID', '42')} protect-main (active)")
    else:
        print("contoso/app: squash=true merge=false rebase=false delete_branch_on_merge=true title=PR_TITLE")
""")


@pytest.fixture
def fake_gh(tmp_path, clean_env):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {**clean_env, "PATH": f"{bindir}:{clean_env['PATH']}", "GH_LOG": str(log)}

    def run(script, *args, **extra):
        r = subprocess.run(["bash", str(KIT / "scripts" / script), *args], cwd=KIT,
                           env={**env, **extra}, capture_output=True, text=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return r, calls

    return run


def test_apply_ruleset_creates_when_missing(fake_gh):
    r, calls = fake_gh("apply-ruleset.sh", "contoso/app")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "created ruleset 42 protect-main (active)"
    get, post = calls
    assert "repos/contoso/app/rulesets?includes_parents=false" in get and "--method" not in get
    assert post[post.index("--method") + 1] == "POST"
    assert "repos/contoso/app/rulesets" in post
    assert "X-GitHub-Api-Version: 2022-11-28" in post


def test_apply_ruleset_updates_by_name_when_it_exists(fake_gh):
    r, calls = fake_gh("apply-ruleset.sh", "contoso/app", FAKE_RULESET_ID="7")
    assert r.returncode == 0, r.stderr
    put = calls[-1]
    assert put[put.index("--method") + 1] == "PUT"
    assert "repos/contoso/app/rulesets/7" in put
    assert r.stdout.strip().startswith("updated ruleset 7")


def test_apply_ruleset_needs_a_repo_argument(fake_gh):
    r, calls = fake_gh("apply-ruleset.sh")
    assert r.returncode != 0 and "usage" in r.stderr and calls == []


def test_configure_repo_sets_squash_only(fake_gh):
    r, calls = fake_gh("configure-repo.sh", "contoso/app")
    assert r.returncode == 0, r.stderr
    (patch,) = calls
    assert patch[patch.index("--method") + 1] == "PATCH" and "repos/contoso/app" in patch
    for field in ("allow_squash_merge=true", "allow_merge_commit=false", "allow_rebase_merge=false",
                  "delete_branch_on_merge=true", "squash_merge_commit_title=PR_TITLE",
                  "squash_merge_commit_message=PR_BODY"):
        assert field in patch
