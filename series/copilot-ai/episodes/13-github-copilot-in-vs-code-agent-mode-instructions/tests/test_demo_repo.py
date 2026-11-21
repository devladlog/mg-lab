"""Tests on the sample workspace that the live demo opens in VS Code."""
import shutil
import subprocess
import sys
from pathlib import Path

from customcheck.rules import check_repo, explain

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "src" / "contoso-vendor-tools"


def run_pytest(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=cwd, capture_output=True, text=True, timeout=120,
    )


def test_workspace_customizations_have_no_errors_or_warnings():
    report = check_repo(WORKSPACE)
    assert report.count("error") == 0, [f.line() for f in report.findings]
    assert report.count("warn") == 0, [f.line() for f in report.findings]
    # the single note is the honest one: the prompt file only runs in Local
    assert [f.code for f in report.findings] == ["PROMPT_LOCAL_ONLY"]


def test_instruction_scoping_for_the_demo_files():
    tests = explain(WORKSPACE, "tests/test_renewals.py")
    cli_py = explain(WORKSPACE, "src/vendor_tools/cli.py")
    renewals = explain(WORKSPACE, "src/vendor_tools/renewals.py")
    assert any("python-tests" in h for h in tests) and not any("cli.instructions" in h for h in tests)
    assert any("cli.instructions" in h for h in cli_py)
    assert len(renewals) == 1


def test_workspace_baseline_tests_pass():
    result = run_pytest(WORKSPACE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 passed" in result.stdout


def test_acceptance_fails_on_baseline_and_passes_with_reference_patch(tmp_path):
    base = run_pytest(WORKSPACE, "acceptance")
    assert base.returncode != 0  # the task is not done yet

    copy = tmp_path / "ws"
    shutil.copytree(WORKSPACE, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    patch = copy / "acceptance" / "reference-solution.patch"
    applied = subprocess.run(["patch", "-p1", "-s", "-i", str(patch)], cwd=copy, capture_output=True, text=True)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    after = run_pytest(copy, "acceptance")
    assert after.returncode == 0, after.stdout + after.stderr
    assert "3 passed" in after.stdout
    # the existing tests still pass with the reference solution
    assert run_pytest(copy).returncode == 0


def test_cli_report_matches_ep2_vendors():
    result = subprocess.run(
        [sys.executable, "-m", "vendor_tools.cli", "--today", "2027-03-01", "--within-days", "400"],
        cwd=WORKSPACE / "src", capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip().endswith("Total: 45,000 EUR")
    assert result.stdout.splitlines()[1].startswith("Fabrikam Cloud")
