"""git bisect run, for real: a repository with a history, the bug introduced in the middle, and the script the recording runs."""
from __future__ import annotations

import re
import subprocess

from conftest import BUGS, copy_app, dotnet_env, needs_bash, needs_dotnet, needs_git


def git(repo, *args: str) -> str:
    result = subprocess.run(["git", "-c", "user.name=Alex Demo", "-c", "user.email=alex.demo@contoso.example",
                             "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                            cwd=repo, env=dotnet_env(), capture_output=True, text=True, timeout=900)
    assert result.returncode == 0, f"git {' '.join(args)}\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


@needs_dotnet
@needs_git
@needs_bash
def test_bisect_finds_the_refactor_that_dropped_the_last_day_of_the_month(tmp_path):
    repo = tmp_path / "history"
    made = subprocess.run(["bash", str(BUGS / "make-history.sh"), str(repo)], capture_output=True, text=True, env=dotnet_env())
    assert made.returncode == 0, made.stdout + made.stderr
    assert "7 commits, good = demo-good, bad = HEAD" in made.stdout
    culprit = git(repo, "log", "--format=%H", "--grep", "compute the last day of the month once")

    # Today's HEAD fails, the first commit passes: let git find the commit in between.
    assert subprocess.run(["bash", "scripts/bisect-repro.sh"], cwd=repo, env=dotnet_env(), capture_output=True).returncode == 1
    git(repo, "bisect", "start", "HEAD", "demo-good")
    out = git(repo, "bisect", "run", "scripts/bisect-repro.sh")

    assert f"{culprit} is the first bad commit" in out, out
    assert "refactor(reports): compute the last day of the month once" in out
    assert "src/Contoso.Orders.Api/Reports.cs | 5 ++---" in out
    steps = len(re.findall(r"^running\b", out, flags=re.M))
    assert 2 <= steps <= 4, f"{steps} steps for 6 commits after the good one\n{out}"
    # The repository is in the bisect state until `git bisect reset`: that is part of the recording.
    assert "bisecting" in git(repo, "status")
    git(repo, "bisect", "reset")
    assert git(repo, "rev-parse", "HEAD") != culprit


def test_make_history_refuses_a_folder_that_is_not_empty(tmp_path):
    (tmp_path / "x.txt").write_text("keep me")
    done = subprocess.run(["bash", str(BUGS / "make-history.sh"), str(tmp_path)], capture_output=True, text=True)
    assert done.returncode == 2 and "is not empty" in done.stderr and (tmp_path / "x.txt").read_text() == "keep me"


@needs_dotnet
@needs_git
def test_a_commit_that_does_not_build_or_has_no_test_is_skipped_not_judged(tmp_path):
    repo = copy_app(tmp_path)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")

    # Does not build: exit 125 ("skip"), which git bisect run understands.
    (repo / "src/Contoso.Orders.Api/Broken.cs").write_text("this is not C#\n", encoding="utf-8")
    broken = subprocess.run(["bash", "scripts/bisect-repro.sh"], cwd=repo, env=dotnet_env(), capture_output=True, text=True)
    assert broken.returncode == 125 and "does not build" in broken.stderr
    (repo / "src/Contoso.Orders.Api/Broken.cs").unlink()

    # The test is not there (an old commit): dotnet test --filter matches nothing and exits 0 on its own.
    tests = repo / "tests/Contoso.Orders.Api.Tests/ReportsTests.cs"
    tests.write_text(tests.read_text().replace("MonthEnd_orders_are_part_of_the_month", "Renamed_away"), encoding="utf-8")
    missing = subprocess.run(["bash", "scripts/bisect-repro.sh"], cwd=repo, env=dotnet_env(), capture_output=True, text=True)
    assert missing.returncode == 125 and "did not run" in missing.stderr
    plain = subprocess.run(["dotnet", "test", "tests/Contoso.Orders.Api.Tests", "--no-build", "--nologo", "--filter",
                            "FullyQualifiedName~MonthEnd_orders_are_part_of_the_month"],
                           cwd=repo, env=dotnet_env(), capture_output=True, text=True)
    assert plain.returncode == 0 and "No test matches" in plain.stdout       # the trap the script guards against
