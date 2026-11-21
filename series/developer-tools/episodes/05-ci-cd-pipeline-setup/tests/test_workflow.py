"""The workflow, checked the way GitHub would read it. There is no local runner for GitHub Actions (and no Docker
here for `act`), so these tests catch what otherwise only fails after a push: schema errors, typos in action
inputs, outputs that don't exist, contexts used where GitHub doesn't allow them, unpinned actions, and the
deploy chain (who can deploy, what gets deployed, what the smoke test expects)."""
from __future__ import annotations

import json
import re

import jsonschema
import pytest
import yaml

from conftest import APP, TESTS, WORKFLOW, action_manifest, load_workflow, pins

WF = load_workflow()
JOBS = WF["jobs"]
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
CONTEXTS = {"github", "env", "vars", "secrets", "needs", "steps", "job", "jobs", "runner", "strategy", "matrix", "inputs"}

# GitHub docs, "Contexts reference" > Context availability (checked 21 Nov 2026).
ALLOWED = {
    "env": {"github", "secrets", "inputs", "vars"},
    "concurrency": {"github", "inputs", "vars"},
    "jobs.if": {"github", "needs", "vars", "inputs"},
    "jobs.concurrency": {"github", "needs", "strategy", "matrix", "inputs", "vars"},
    "jobs.outputs": {"github", "needs", "strategy", "matrix", "job", "runner", "env", "vars", "secrets", "steps", "inputs"},
    "jobs.environment.url": {"github", "needs", "strategy", "matrix", "job", "runner", "env", "vars", "steps", "inputs"},
    "steps.with": {"github", "needs", "strategy", "matrix", "job", "runner", "env", "vars", "secrets", "steps", "inputs"},
    "steps.env": {"github", "needs", "strategy", "matrix", "job", "runner", "env", "vars", "secrets", "steps", "inputs"},
}


def contexts_in(value) -> set[str]:
    """Context names referenced inside ${{ }} (string literals removed first)."""
    found = set()
    for expr in EXPR.findall(str(value)):
        expr = re.sub(r"'[^']*'", "", expr)
        for m in re.finditer(r"(?<![\w.])([A-Za-z_][\w-]*)\s*(?=[.\[])", expr):
            if m.group(1) in CONTEXTS:
                found.add(m.group(1))
    return found


def steps():
    for job_id, job in JOBS.items():
        for i, step in enumerate(job.get("steps", [])):
            yield job_id, i, step


# ------------------------------------------------------------------------------------------- structure
def test_matches_the_github_workflow_schema():
    schema = json.loads((TESTS / "schemas" / "github-workflow.json").read_text())
    jsonschema.validate(WF, schema)


def test_dependabot_config_matches_its_schema_and_watches_the_actions():
    config = yaml.safe_load((APP / ".github" / "dependabot.yml").read_text())
    jsonschema.validate(config, json.loads((TESTS / "schemas" / "dependabot-2.0.json").read_text()))
    assert {"package-ecosystem": "github-actions", "directory": "/"}.items() <= config["updates"][0].items()


def test_job_names_equal_ids_so_required_checks_stay_stable():
    # Rulesets (episode 1) require checks by name; a renamed job would block every PR.
    assert {j: v.get("name") for j, v in JOBS.items()} == {j: j for j in JOBS}


def test_pipeline_graph():
    needs = {j: sorted([v["needs"]] if isinstance(v.get("needs"), str) else v.get("needs", [])) for j, v in JOBS.items()}
    assert needs == {
        "guardrails": [], "build-test": [], "e2e": ["build-test"],
        "publish": ["build-test", "e2e", "guardrails"], "deploy": ["publish"],
    }


def test_every_job_has_a_timeout():
    assert all(isinstance(j.get("timeout-minutes"), int) and j["timeout-minutes"] <= 20 for j in JOBS.values())


# ------------------------------------------------------------------------------------------- actions
USES = [(j, i, s["uses"]) for j, i, s in steps() if "uses" in s]


@pytest.mark.parametrize("job,index,uses", USES, ids=[f"{j}[{i}]" for j, i, _ in USES])
def test_actions_are_pinned_to_the_recorded_commit(job, index, uses):
    action, _, ref = uses.partition("@")
    assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{uses}: pin a full commit SHA, tags can move"
    assert pins()[action]["sha"] == ref
    line = next(l for l in WORKFLOW.read_text().splitlines() if uses in l)
    assert line.rstrip().endswith(f"# {pins()[action]['tag']}"), "keep the version comment (Dependabot updates it)"


@pytest.mark.parametrize("job,index,uses", USES, ids=[f"{j}[{i}]" for j, i, _ in USES])
def test_with_inputs_exist_in_the_pinned_action(job, index, uses):
    manifest = action_manifest(uses.split("@")[0])
    inputs = manifest.get("inputs") or {}
    given = set((JOBS[job]["steps"][index].get("with") or {}))
    assert given <= set(inputs), f"unknown inputs: {given - set(inputs)}"
    required = {k for k, v in inputs.items() if v.get("required") in (True, "true") and "default" not in v}
    assert required <= given, f"missing required inputs: {required - given}"


def test_step_output_references_exist():
    for job_id, job in JOBS.items():
        ids = {s["id"]: s for s in job.get("steps", []) if "id" in s}
        text = yaml.safe_dump(job)
        for step_id, output in re.findall(r"steps\.([\w-]+)\.outputs\.([\w-]+)", text):
            assert step_id in ids, f"{job_id}: no step with id {step_id}"
            outputs = action_manifest(ids[step_id]["uses"].split("@")[0]).get("outputs") or {}
            assert output in outputs, f"{job_id}: {ids[step_id]['uses']} has no output {output}"


def test_needs_output_references_exist_and_are_in_needs():
    for job_id, job in JOBS.items():
        needs = [job["needs"]] if isinstance(job.get("needs"), str) else job.get("needs", [])
        for other, output in re.findall(r"needs\.([\w-]+)\.outputs\.([\w-]+)", yaml.safe_dump(job)):
            assert other in needs, f"{job_id} reads {other} but doesn't need it"
            assert output in JOBS[other].get("outputs", {}), f"{other} has no output {output}"


# ------------------------------------------------------------------------------------------- expressions
def locations():
    yield "env", WF.get("env", {})
    yield "concurrency", WF.get("concurrency", {})
    for job_id, job in JOBS.items():
        yield "jobs.if", job.get("if", "")
        yield "jobs.concurrency", job.get("concurrency", {})
        yield "jobs.outputs", job.get("outputs", {})
        env = job.get("environment")
        yield "jobs.environment.url", env.get("url", "") if isinstance(env, dict) else ""
        for step in job.get("steps", []):
            yield "steps.with", step.get("with", {})
            yield "steps.env", step.get("env", {})


def test_contexts_are_only_used_where_github_allows_them():
    for where, value in locations():
        used = contexts_in(value)
        assert used <= ALLOWED[where], f"{where}: {used - ALLOWED[where]} not available there ({value})"


def test_the_context_checker_catches_a_real_mistake():
    assert contexts_in("${{ env.IMAGE != '' }}") == {"env"}
    assert not contexts_in("${{ env.IMAGE }}") <= ALLOWED["jobs.if"]       # env isn't available in jobs.<id>.if
    assert contexts_in("${{ format('{0}', 'secrets.X') }}") == set()        # inside a string literal


def test_no_expressions_inside_run_scripts():
    # Script injection (episode 1): untrusted values go through env:, never ${{ }} pasted into a shell.
    offenders = [(j, s.get("name", s["run"][:40])) for j, _, s in steps() if "run" in s and "${{" in s["run"]]
    assert offenders == []


# ------------------------------------------------------------------------------------------- permissions
def test_token_is_read_only_unless_a_job_asks():
    assert WF["permissions"] == {"contents": "read"}
    asked = {j: v["permissions"] for j, v in JOBS.items() if "permissions" in v}
    assert asked == {
        "publish": {"contents": "read", "packages": "write", "id-token": "write", "attestations": "write"},
        "deploy": {"contents": "read", "id-token": "write"},
    }


def test_publish_and_deploy_never_run_for_pull_requests():
    assert JOBS["publish"]["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert JOBS["deploy"]["needs"] == "publish"          # skipped when publish is skipped
    assert WF["on"]["push"] == {"branches": ["main"]}


def test_deploy_is_gated_by_the_production_environment_and_never_cancelled():
    deploy = JOBS["deploy"]
    assert deploy["environment"]["name"] == "production"
    assert deploy["concurrency"] == {"group": "deploy-production", "cancel-in-progress": False}
    # azure/login reads environment secrets: released only after a required reviewer approves.
    login = next(s for s in deploy["steps"] if s.get("uses", "").startswith("azure/login@"))
    assert set(login["with"].values()) == {"${{ secrets.AZURE_CLIENT_ID }}", "${{ secrets.AZURE_TENANT_ID }}",
                                           "${{ secrets.AZURE_SUBSCRIPTION_ID }}"}
    assert "creds" not in login["with"]                  # no client secret JSON: OIDC only


def test_main_runs_are_never_cancelled_but_pr_runs_are():
    assert WF["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


# ------------------------------------------------------------------------------------------- what ships
def test_deploy_ships_the_image_publish_built_and_the_smoke_test_expects_that_commit():
    publish, deploy = JOBS["publish"], JOBS["deploy"]
    build = next(s for s in publish["steps"] if s.get("id") == "build")
    meta = next(s for s in publish["steps"] if s.get("id") == "meta")
    assert "type=sha,format=long" in meta["with"]["tags"]                      # tag sha-<40 hex>
    assert publish["outputs"]["image"] == "${{ env.IMAGE }}:sha-${{ github.sha }}"
    assert build["with"]["build-args"] == "APP_VERSION=${{ github.sha }}"      # /healthz reports it
    webapp = next(s for s in deploy["steps"] if s.get("id") == "deploy")
    assert webapp["with"]["images"] == "${{ needs.publish.outputs.image }}"
    smoke = deploy["steps"][-1]
    assert smoke["env"]["VERSION"] == "${{ github.sha }}" and '--version "$VERSION"' in smoke["run"]
    assert "--read-only" in smoke["run"]                                      # no test data in production


def test_attestation_is_for_the_pushed_digest_without_a_tag():
    attest = next(s for s in JOBS["publish"]["steps"] if s.get("uses", "").startswith("actions/attest@"))
    assert attest["with"] == {"subject-name": "${{ env.IMAGE }}",            # GitHub docs: no tag in the name
                              "subject-digest": "${{ steps.build.outputs.digest }}", "push-to-registry": True}


def test_e2e_runs_the_same_script_as_a_laptop_and_passes_the_commit():
    step = next(s for s in JOBS["e2e"]["steps"] if s.get("run") == "scripts/e2e.sh")
    assert step["env"] == {"APP_VERSION": "${{ github.sha }}"}


def test_restore_is_locked_and_cached_on_the_lock_files():
    lock_files = sorted(p.relative_to(APP).as_posix() for p in APP.glob("**/packages.lock.json")
                        if "obj" not in p.parts and "bin" not in p.parts)
    csprojs = sorted(p.relative_to(APP).parent.as_posix() for p in APP.glob("**/*.csproj"))
    assert [p.rsplit("/", 1)[0] for p in lock_files] == csprojs               # one lock file per project
    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in (APP / "Directory.Build.props").read_text()
    for job in ("build-test", "e2e"):
        setup = next(s for s in JOBS[job]["steps"] if s.get("uses", "").startswith("actions/setup-dotnet@"))
        assert setup["with"] == {"global-json-file": "global.json", "cache": True,
                                 "cache-dependency-path": "**/packages.lock.json"}
        assert "dotnet restore --locked-mode" in [s.get("run") for s in JOBS[job]["steps"]]


def test_test_results_are_summarised_and_kept_even_when_tests_fail():
    s = JOBS["build-test"]["steps"]
    summary = next(x for x in s if x.get("name") == "Test summary")
    upload = next(x for x in s if x.get("uses", "").startswith("actions/upload-artifact@"))
    assert summary["if"] == upload["if"] == "${{ !cancelled() }}"
    assert summary["run"] == "python3 tools/trx_check.py TestResults/unit.trx"


# ------------------------------------------------------------------------------------------- the checks catch mistakes
def unknown_inputs(wf: dict) -> list[str]:
    out = []
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                inputs = action_manifest(step["uses"].split("@")[0]).get("inputs") or {}
                out += [f"{step['uses'].split('@')[0]}:{k}" for k in (step.get("with") or {}) if k not in inputs]
    return out


def test_a_typo_in_an_action_input_is_caught(tmp_path):
    broken = WORKFLOW.read_text().replace("cache-dependency-path:", "cache-dependency-paths:", 1)
    (tmp_path / "ci-cd.yml").write_text(broken)
    assert unknown_inputs(load_workflow()) == []
    assert unknown_inputs(load_workflow(tmp_path / "ci-cd.yml")) == ["actions/setup-dotnet:cache-dependency-paths"]

