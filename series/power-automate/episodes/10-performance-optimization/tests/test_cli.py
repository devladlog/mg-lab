import subprocess
import sys

from conftest import FAST, SLOW, SRC


def run(*args):
    return subprocess.run([sys.executable, "-m", "perfkit", *map(str, args)], cwd=SRC, capture_output=True, text=True)


def test_lint_slow_exit_zero_with_warnings():
    r = run("lint", SLOW)
    assert r.returncode == 0 and "4 finding(s)" in r.stdout and "P03" in r.stdout


def test_lint_fast():
    r = run("lint", FAST)
    assert r.returncode == 0 and "0 finding(s)" in r.stdout


def test_lint_exit_one_on_error(tmp_path, fast):
    from conftest import loop_of
    import json
    loop_of(fast)["runtimeConfiguration"]["concurrency"]["repetitions"] = 99
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(fast))
    assert run("lint", p).returncode == 1


def test_cost():
    r = run("cost", FAST, "--items", "1000")
    assert "406 actions" in r.stdout and "401 SharePoint calls" in r.stdout


def test_compare_flags_over_budget():
    r = run("compare", SLOW, FAST)
    assert r.returncode == 0
    assert "2806" in r.stdout and "11206" in r.stdout and "slow OVER, fast ok" in r.stdout


def test_usage():
    assert run().returncode == 2
