"""Review metrics. The JSON fixtures have the shape of GitHub's documented REST responses (invented values); `gh` is a
small fake that serves them, so `fetch` runs for real against its command line."""
from __future__ import annotations

import os
import stat
import sys

import pytest

from conftest import CLI, FIXTURES, load_json
from review_kit import metrics

GH = FIXTURES / "github"


def pr(n):
    return load_json(GH / f"pull-{n}.json")


def reviews(n):
    return load_json(GH / f"reviews-{n}.json")


def test_first_review_ignores_the_author_and_pending_drafts():
    row = metrics.compute(pr(1), reviews(1))
    assert row["hours_to_first_review"] == 3.0          # sam-demo, 10:15 -> 13:15; alex-demo's own comment doesn't count
    assert row["hours_to_merge"] == 26.0
    assert (row["changes_requested"], row["approvals"], row["reviewers"]) == (1, 2, ["riley-demo", "sam-demo"])
    assert row["lines"] == 31 and row["merged"]


def test_a_pull_request_nobody_else_reviewed_has_no_first_review_time():
    row = metrics.compute(pr(2), reviews(2))
    assert row["hours_to_first_review"] is None and row["reviewers"] == []      # PENDING + author only
    assert row["hours_to_merge"] == 0.5


def test_closed_without_merge_and_missing_sizes():
    p = pr(3)
    del p["additions"]
    row = metrics.compute(p, reviews(3))
    assert row["merged"] is False and row["hours_to_merge"] is None and row["lines"] is None
    assert row["hours_to_first_review"] == 1.5


def test_median_and_table():
    rows = [metrics.compute(pr(n), reviews(n)) for n in (1, 2, 3)]
    assert metrics.median(rows, "hours_to_first_review") == 2.25      # median of 3.0 and 1.5; #2 has none
    assert metrics.median(rows, "hours_to_merge") == 13.25
    text = metrics.render(rows)
    assert "| #1 | 31 | 3.0 | 26.0 | 1 | riley-demo, sam-demo |" in text
    assert "Never reviewed by anyone but the author: #2" in text and "#3" not in text.split("Never reviewed")[1]


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    """A `gh` on PATH that answers `gh api <endpoint>` from the fixtures and records what it was asked."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "gh.log"
    script = bindir / "gh"
    script.write_text(f"""#!{sys.executable}
import sys, pathlib
GH = pathlib.Path({str(GH)!r})
args = sys.argv[1:]
pathlib.Path({str(log)!r}).open("a").write(" ".join(args) + "\\n")
assert args[0] == "api", args
ep = args[1]
if ep.startswith("repos/contoso/orders/pulls?"):
    sys.stdout.write((GH / "pulls-list.json").read_text())
elif ep.endswith("/reviews?per_page=100"):
    sys.stdout.write((GH / ("reviews-" + ep.split("/")[-2] + ".json")).read_text())
elif "/pulls/" in ep:
    sys.stdout.write((GH / ("pull-" + ep.rsplit("/", 1)[-1] + ".json")).read_text())
else:
    sys.stderr.write("HTTP 404: Not Found"); sys.exit(1)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return log


def test_fetch_asks_for_the_list_then_each_pull_request_and_its_reviews(fake_gh):
    rows = metrics.fetch("contoso/orders", limit=2)
    assert [r["number"] for r in rows] == [1, 2]
    asked = fake_gh.read_text().splitlines()
    assert asked[0] == "api repos/contoso/orders/pulls?state=closed&per_page=2&sort=updated&direction=desc"
    assert "api repos/contoso/orders/pulls/1" in asked and "api repos/contoso/orders/pulls/1/reviews?per_page=100" in asked


def test_cli_metrics_end_to_end_with_json_output(fake_gh):
    import json
    import subprocess
    res = subprocess.run([sys.executable, str(CLI), "metrics", "--repo", "contoso/orders", "--json"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert [r["hours_to_first_review"] for r in json.loads(res.stdout)] == [3.0, None, 1.5]


def test_a_failing_gh_is_a_clean_error(fake_gh):
    import subprocess
    res = subprocess.run([sys.executable, str(CLI), "metrics", "--repo", "contoso/missing"], capture_output=True, text=True)
    assert res.returncode == 2 and "failed" in res.stderr
