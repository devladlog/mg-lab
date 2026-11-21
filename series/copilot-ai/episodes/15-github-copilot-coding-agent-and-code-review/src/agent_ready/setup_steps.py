"""Validate .github/workflows/copilot-setup-steps.yml against what GitHub documents for Copilot cloud agent.

Source: docs.github.com, "Customize the agent environment" (read 21 Nov 2026). Rules encoded here:
  - the job MUST be called copilot-setup-steps
  - only steps, permissions, runs-on, services, snapshot and timeout-minutes are honored; the rest is ignored
  - timeout-minutes maximum is 59
  - if steps clone the repo, permissions needs contents: read
  - fetch-depth on actions/checkout is overridden by the agent
  - only Ubuntu x64 and Windows 64-bit runners are supported; the integrated firewall is not compatible with Windows
  - the docs advise against running the workflow on both push and pull_request in a real project
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .findings import Finding

JOB_NAME = "copilot-setup-steps"
HONORED_KEYS = {"steps", "permissions", "runs-on", "services", "snapshot", "timeout-minutes"}
MAX_TIMEOUT = 59


def _triggers(doc: dict) -> set[str]:
    # PyYAML (YAML 1.1) reads the key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    if isinstance(on, dict):
        return set(on)
    return set()


def _runs_on_text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values())
    return str(value)


def check_text(text: str) -> list[Finding]:
    out: list[Finding] = []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [Finding("error", "yaml", f"not valid YAML: {exc}")]
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return [Finding("error", "no-jobs", "the workflow has no `jobs:` mapping")]

    jobs = doc["jobs"]
    if JOB_NAME not in jobs:
        names = ", ".join(sorted(jobs)) or "none"
        return [Finding("error", "job-name", f"the job must be called `{JOB_NAME}` or Copilot will not pick it up (found: {names})")]

    job = jobs[JOB_NAME]
    if not isinstance(job, dict):
        return [Finding("error", "job-shape", f"`{JOB_NAME}` must be a mapping")]

    for key in sorted(set(job) - HONORED_KEYS):
        out.append(Finding("warning", "ignored-key", f"`{key}` is ignored: only {', '.join(sorted(HONORED_KEYS))} are honored"))

    steps = job.get("steps") or []
    if not steps:
        out.append(Finding("warning", "no-steps", "no steps: Copilot will have to discover and install dependencies by trial and error"))

    timeout = job.get("timeout-minutes")
    if timeout is None:
        out.append(Finding("info", "timeout", f"no timeout-minutes: sessions are limited to {MAX_TIMEOUT} minutes anyway; set a shorter one to fail fast"))
    elif isinstance(timeout, int):
        if timeout > MAX_TIMEOUT:
            out.append(Finding("error", "timeout", f"timeout-minutes {timeout} is above the maximum of {MAX_TIMEOUT}"))
    else:
        out.append(Finding("warning", "timeout", f"timeout-minutes should be a whole number up to {MAX_TIMEOUT}, got {timeout!r}"))

    perms = job.get("permissions", doc.get("permissions"))
    uses_checkout = any(isinstance(s, dict) and str(s.get("uses", "")).startswith("actions/checkout") for s in steps)
    if perms is None:
        out.append(Finding("warning", "permissions", "no permissions: set the lowest level the steps need (contents: read if they clone the repo)"))
    elif isinstance(perms, str):
        if perms == "write-all":
            out.append(Finding("warning", "permissions", "write-all is far more than setup steps need"))
    elif isinstance(perms, dict):
        writes = sorted(k for k, v in perms.items() if v == "write")
        if writes:
            out.append(Finding("warning", "permissions", f"write access to {', '.join(writes)}: setup steps rarely need it"))
        if uses_checkout and perms.get("contents") != "read" and perms.get("contents") != "write":
            out.append(Finding("error", "checkout-permission", "a step clones the repo but permissions has no `contents: read`"))

    for step in steps:
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout"):
            if "fetch-depth" in (step.get("with") or {}):
                out.append(Finding("info", "fetch-depth", "fetch-depth is overridden by the agent so it can roll back commits"))

    runs_on = _runs_on_text(job.get("runs-on", ""))
    low = runs_on.lower()
    if "macos" in low:
        out.append(Finding("error", "runner", "macOS runners are not supported by Copilot cloud agent (Ubuntu x64 and Windows 64-bit only)"))
    elif "windows" in low:
        out.append(Finding("warning", "runner", "the integrated firewall is not compatible with Windows: use self-hosted runners or larger runners with Azure private networking"))
    elif not runs_on:
        out.append(Finding("warning", "runner", "no runs-on: the default hosted runner will be used"))

    triggers = _triggers(doc)
    if {"push", "pull_request"} <= triggers:
        out.append(Finding("warning", "triggers", "both push and pull_request: the docs advise against this in a real project (the check runs twice)"))
    if "workflow_dispatch" not in triggers:
        out.append(Finding("info", "triggers", "add workflow_dispatch so the file can be run by hand from the Actions tab once it is on the default branch"))
    return out


def check_file(path: str | Path) -> list[Finding]:
    return check_text(Path(path).read_text(encoding="utf-8"))
