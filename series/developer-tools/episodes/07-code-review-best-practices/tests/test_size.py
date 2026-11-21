"""PR size, measured on real git history in throwaway repositories (not on made-up numstat strings)."""
from __future__ import annotations

import pytest

from conftest import commit, git, needs_git, new_repo, run_cli, write
from review_kit import size

pytestmark = needs_git


def lines(n: int, prefix: str = "line") -> str:
    return "".join(f"{prefix} {i}\n" for i in range(n))


def test_labels_at_the_boundaries():
    assert [size.label_for(n) for n in (0, 100, 101, 300, 301, 600, 601)] == ["S", "S", "M", "M", "L", "L", "XL"]


def test_numstat_from_real_git_counts_added_and_deleted_lines(tmp_path):
    repo = new_repo(tmp_path / "r", {"src/a.cs": lines(10)})
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "feat: change", {"src/a.cs": lines(3) + lines(5, "new"), "src/b.cs": lines(4)})
    changes = size.diff_numstat("main", "feature", cwd=str(repo))
    by_path = {c.path: (c.added, c.deleted) for c in changes}
    assert by_path == {"src/a.cs": (5, 7), "src/b.cs": (4, 0)}


def test_a_renamed_file_is_one_change_not_a_delete_and_an_add(tmp_path):
    repo = new_repo(tmp_path / "r", {"old/Orders.cs": lines(40)})
    git(repo, "switch", "-q", "-c", "feature")
    (repo / "src").mkdir()
    git(repo, "mv", "old/Orders.cs", "src/Orders.cs")
    commit(repo, "refactor: move")
    [c] = size.diff_numstat("main", "feature", cwd=str(repo))
    assert (c.path, c.renamed_from, c.lines) == ("src/Orders.cs", "old/Orders.cs", 0)


def test_binary_files_are_listed_but_have_no_lines(tmp_path):
    repo = new_repo(tmp_path / "r")
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "docs: logo", {"docs/logo.png": bytes(range(256)) * 4})
    report = size.analyze(size.diff_numstat("main", "feature", cwd=str(repo)))
    assert report.lines == 0 and report.counted[0].binary
    assert "Binary files" in size.render(report)


def test_three_dots_ignore_what_happened_on_main_after_the_branch_was_cut(tmp_path):
    repo = new_repo(tmp_path / "r", {"a.txt": "a\n"})
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "feat: mine", {"mine.txt": lines(7)})
    git(repo, "switch", "-q", "main")
    commit(repo, "feat: someone else's work", {"other.txt": lines(500)})
    report = size.analyze(size.diff_numstat("main", "feature", cwd=str(repo)))
    assert [c.path for c in report.counted] == ["mine.txt"] and report.label == "S"


def test_lock_files_generated_code_and_snapshots_are_not_counted(tmp_path):
    repo = new_repo(tmp_path / "r")
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "chore: bump", {
        "src/Api/packages.lock.json": lines(900), "web/package-lock.json": lines(900), "src/Model.g.cs": lines(900),
        "tests/__snapshots__/a.snap": lines(900), "web/node_modules/x/index.js": lines(900), "src/Api/Real.cs": lines(30)})
    report = size.analyze(size.diff_numstat("main", "feature", cwd=str(repo)))
    assert (report.lines, report.label, len(report.ignored)) == (30, "S", 5)


def test_areas_are_ranked_and_a_big_pull_request_gets_a_split_hint(tmp_path):
    repo = new_repo(tmp_path / "r")
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "feat: everything", {"src/Api/A.cs": lines(400), "src/Api/B.cs": lines(100),
                                      "tests/Api.Tests/T.cs": lines(150), "README.md": lines(3)})
    report = size.analyze(size.diff_numstat("main", "feature", cwd=str(repo)))
    assert report.by_area() == [("src/Api", 2, 500), ("tests/Api.Tests", 1, 150), ("(repo root)", 1, 4)]
    text = size.render(report)
    assert report.label == "XL" and "Consider splitting along these areas: src/Api (500)" in text


def test_cli_fails_above_the_limit_and_writes_the_github_output_and_summary(tmp_path):
    repo = new_repo(tmp_path / "r")
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "feat: big", {"src/Api/A.cs": lines(700)})
    out, summary = tmp_path / "out.txt", tmp_path / "summary.md"
    res = run_cli("size", "--base", "main", "--head", "feature", "--fail-above", "L", cwd=repo,
                  env={"GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary)})
    assert res.returncode == 1 and "size/XL is above size/L" in res.stdout
    assert out.read_text() == "label=size/XL\nlines=700\n"
    assert summary.read_text().startswith("size/XL: 700 changed lines")
    ok = run_cli("size", "--base", "main", "--head", "feature", "--fail-above", "L", cwd=repo,
                 env={"GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": ""})
    assert ok.returncode == 1                                      # still XL: the env vars only control the side files
    write(repo, {"src/Api/A.cs": lines(50)})
    commit(repo, "fix: smaller")
    assert run_cli("size", "--base", "main", "--head", "feature", "--fail-above", "L", cwd=repo,
                   env={"GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": ""}).returncode == 0


def test_a_bad_revision_is_a_usage_error_not_a_crash(tmp_path):
    repo = new_repo(tmp_path / "r")
    res = run_cli("size", "--base", "nope", "--head", "main", cwd=repo)
    assert res.returncode == 2 and "git diff failed" in res.stderr
