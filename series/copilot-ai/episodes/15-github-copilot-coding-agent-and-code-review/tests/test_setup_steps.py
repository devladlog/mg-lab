from agent_ready import setup_steps as ss

GOOD = """
name: Copilot Setup Steps
on:
  workflow_dispatch:
  pull_request:
    paths: [.github/workflows/copilot-setup-steps.yml]
jobs:
  copilot-setup-steps:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - run: dotnet restore
"""


def codes(text):
    return {(f.level, f.code) for f in ss.check_text(text)}


def test_demo_repo_file_is_clean(demo):
    assert ss.check_file(demo / ".github/workflows/copilot-setup-steps.yml") == []


def test_good_file_has_no_findings():
    assert ss.check_text(GOOD) == []


def test_wrong_job_name_is_an_error():
    text = GOOD.replace("copilot-setup-steps:\n    runs-on", "setup:\n    runs-on")
    f = ss.check_text(text)
    assert f[0].level == "error" and f[0].code == "job-name" and "setup" in f[0].message


def test_timeout_above_59_is_an_error():
    assert ("error", "timeout") in codes(GOOD.replace("timeout-minutes: 20", "timeout-minutes: 90"))


def test_timeout_59_is_fine():
    assert ("error", "timeout") not in codes(GOOD.replace("timeout-minutes: 20", "timeout-minutes: 59"))


def test_ignored_keys_are_reported():
    text = GOOD.replace("    permissions:", "    env:\n      A: b\n    container: node:20\n    permissions:")
    msgs = [f.message for f in ss.check_text(text) if f.code == "ignored-key"]
    assert len(msgs) == 2 and any("`env`" in m for m in msgs) and any("`container`" in m for m in msgs)


def test_checkout_without_contents_read_is_an_error():
    text = GOOD.replace("    permissions:\n      contents: read\n", "    permissions:\n      issues: read\n")
    assert ("error", "checkout-permission") in codes(text)


def test_no_permissions_is_a_warning_and_write_is_flagged():
    nop = GOOD.replace("    permissions:\n      contents: read\n", "")
    assert ("warning", "permissions") in codes(nop)
    w = GOOD.replace("contents: read", "contents: write")
    assert ("warning", "permissions") in codes(w)


def test_macos_runner_is_an_error_windows_is_a_warning():
    assert ("error", "runner") in codes(GOOD.replace("ubuntu-latest", "macos-latest"))
    assert ("warning", "runner") in codes(GOOD.replace("ubuntu-latest", "windows-latest"))


def test_push_and_pull_request_together_warn():
    text = GOOD.replace("on:\n  workflow_dispatch:", "on:\n  push:\n  workflow_dispatch:")
    assert ("warning", "triggers") in codes(text)


def test_missing_workflow_dispatch_is_info():
    text = GOOD.replace("  workflow_dispatch:\n", "")
    assert ("info", "triggers") in codes(text)


def test_fetch_depth_is_reported_as_overridden():
    text = GOOD.replace("- uses: actions/checkout@v4", "- uses: actions/checkout@v4\n        with:\n          fetch-depth: 1")
    assert ("info", "fetch-depth") in codes(text)


def test_invalid_yaml_and_no_jobs():
    assert ss.check_text("a: [")[0].code == "yaml"
    assert ss.check_text("name: x")[0].code == "no-jobs"
