"""tools/trx_check.py and tools/oidc_subject.py: small tools, real inputs (TRX files written by `dotnet test` here)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

import oidc_subject
import trx_check
from conftest import APP, FIXTURES

TRX = FIXTURES / "trx"


# ------------------------------------------------------------------------------------------- trx_check
def test_skipped_tests_are_counted_even_though_the_counters_say_zero():
    # Real file: 21 passed, 4 skipped. Its <Counters> has notExecuted="0"; total - executed is the truth.
    assert 'notExecuted="0"' in (TRX / "unit-with-skips.trx").read_text()
    c = trx_check.counts(str(TRX / "unit-with-skips.trx"))
    assert (c["passed"], c["skipped"], c["failed"]) == (21, 4, 0)


def test_green_unit_run_passes_but_not_when_skips_are_forbidden(capsys):
    assert trx_check.main([str(TRX / "unit-with-skips.trx")]) == 0
    assert trx_check.main([str(TRX / "unit-with-skips.trx"), "--no-skipped"]) == 1
    assert "4 test(s) skipped" in capsys.readouterr().err


def test_sql_server_tests_that_all_skipped_fail_the_e2e_gate(capsys):
    # What `dotnet test --filter Category=SqlServer` writes when ORDERS_SQLSERVER_TESTS isn't set: exit code 0.
    assert trx_check.main([str(TRX / "sqlserver-all-skipped.trx"), "--min-passed", "4", "--no-skipped"]) == 1
    err = capsys.readouterr().err
    assert "only 0 passed, expected at least 4" in err and "4 test(s) skipped" in err


def test_writes_the_github_job_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    trx_check.main([str(TRX / "unit-with-skips.trx")])
    assert "| unit-with-skips.trx | 21 | 0 | 4 |" in summary.read_text()


def test_not_a_trx_file_is_an_error(tmp_path):
    bad = tmp_path / "x.trx"
    bad.write_text("<TestRun/>")
    with pytest.raises(ValueError, match="not a .trx"):
        trx_check.counts(str(bad))


# ------------------------------------------------------------------------------------------- oidc_subject
REPO = {"name": "orders-app-ci-demo", "id": 456789, "owner": {"login": "contoso", "id": 123456},
        "created_at": "2026-11-21T10:00:00Z"}


def test_new_repositories_get_the_immutable_subject():
    assert oidc_subject.subject(REPO, environment="production") == \
        "repo:contoso@123456/orders-app-ci-demo@456789:environment:production"


def test_repositories_created_before_15_july_2026_keep_the_name_based_subject():
    old = dict(REPO, created_at="2025-03-01T08:00:00Z")
    assert oidc_subject.subject(old, environment="production") == "repo:contoso/orders-app-ci-demo:environment:production"


@pytest.mark.parametrize("fmt,expected", [
    # Microsoft Learn (Entra workload identity federation) and the Azure Databricks GitHub page give these shapes.
    ("legacy", "repo:octo-org/octo-repo:environment:Production"),
    ("immutable", "repo:octo-org@123456/octo-repo@456789:environment:Production"),
])
def test_matches_the_documented_shapes_and_keeps_case(fmt, expected):
    repo = {"name": "octo-repo", "id": 456789, "owner": {"login": "octo-org", "id": 123456},
            "created_at": "2026-08-01T00:00:00Z"}
    assert oidc_subject.subject(repo, environment="Production", fmt=fmt) == expected   # matching is case-sensitive


def test_branch_subject_for_jobs_without_an_environment():
    assert oidc_subject.subject(REPO, ref="refs/heads/main", fmt="legacy") == \
        "repo:contoso/orders-app-ci-demo:ref:refs/heads/main"
    with pytest.raises(ValueError):
        oidc_subject.subject(REPO, environment="production", ref="refs/heads/main")


def test_cli_reads_gh_api_json_from_stdin():
    out = subprocess.run([sys.executable, str(APP / "tools" / "oidc_subject.py"), "--environment", "production"],
                         input=json.dumps(REPO), capture_output=True, text=True, check=True).stdout
    assert out.strip() == "repo:contoso@123456/orders-app-ci-demo@456789:environment:production"
