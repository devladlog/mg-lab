from __future__ import annotations

import pytest

from conftest import APP, commit, git, needs_git, new_repo, run_cli
from review_kit import owners

CODEOWNERS = (APP / ".github" / "CODEOWNERS").read_text()
RULES, WARNINGS = owners.parse(CODEOWNERS)


def who(path: str, rules=RULES) -> tuple[str, ...]:
    return owners.owners_for(path, rules)


def test_the_shipped_codeowners_file_parses_without_warnings():
    assert WARNINGS == [] and len(RULES) == 5


@pytest.mark.parametrize("path,expected", [
    ("README.md", ("@contoso/dev-team",)),
    ("src/Contoso.Orders.Api/Program.cs", ("@contoso/orders-team",)),
    ("src/Contoso.Orders.Api/Properties/launchSettings.json", ("@contoso/orders-team",)),
    ("tests/Contoso.Orders.Api.Tests/CancelTests.cs", ("@contoso/orders-team", "@contoso/qa")),
    (".github/workflows/pr-review-kit.yml", ("@contoso/platform-team",)),
    ("tools/review_kit/size.py", ("@contoso/platform-team",)),
    ("tools/other/x.py", ("@contoso/dev-team",)),
])
def test_last_matching_pattern_wins_on_the_shipped_file(path, expected):
    assert who(path) == expected


def rules(text):
    r, w = owners.parse(text)
    assert w == []
    return r


def test_gitignore_style_patterns():
    r = rules("*.md @docs\n/build/ @ci\ndocs/ @writers\n**/Migrations/ @dba\n/src/*.cs @top\n")
    assert who("README.md", r) == ("@docs",) and who("a/b/c.md", r) == ("@docs",)
    assert who("build/x/y.bin", r) == ("@ci",) and who("sub/build/x.bin", r) == ()      # anchored with a leading slash
    assert who("docs/a.txt", r) == ("@writers",) and who("x/docs/a.txt", r) == ("@writers",)   # not anchored
    assert who("src/Data/Migrations/001.cs", r) == ("@dba",) and who("Migrations/001.cs", r) == ("@dba",)
    assert who("src/a.cs", r) == ("@top",) and who("src/sub/a.cs", r) == ()               # * does not cross a slash


def test_paths_are_case_sensitive():
    r = rules("/Docs/ @writers\n")
    assert who("Docs/a.md", r) == ("@writers",) and who("docs/a.md", r) == ()


def test_a_pattern_with_no_owner_removes_the_owner_for_those_files():
    r = rules("* @everyone\n/apps/github\n")
    assert who("apps/github", r) == () and who("apps/other", r) == ("@everyone",)


def test_owners_split_over_two_lines_are_not_added_together():
    r = rules("/api/ @a\n/api/ @b\n")
    assert who("api/x.cs", r) == ("@b",)                 # GitHub: if split across lines, only the last-listed line applies


def test_unsupported_syntax_and_bad_owners_are_warnings_and_those_lines_are_skipped():
    r, w = owners.parse("* @all\n!/keep/ @x\n/[ab]/ @y\n\\#hash @z\n/bad/ notanowner\n/mail/ docs@contoso.example\n")
    assert [x.pattern for x in r] == ["*", "/mail/"]
    assert len(w) == 4 and all("GitHub skips the line" in x for x in w)
    assert who("mail/x", r) == ("docs@contoso.example",)


def test_comments_and_blank_lines_are_ignored():
    r = rules("# a comment\n\n   \n* @all  # trailing comment\n")
    assert who("x", r) == ("@all",)


def test_route_groups_files_by_owner_set_and_lists_the_unowned():
    r = rules("/src/ @a\n/docs/ @b @c\n")
    routing = owners.route(["src/x.cs", "docs/y.md", "loose.txt", "src/z.cs"], r)
    assert routing == {("@a",): ["src/x.cs", "src/z.cs"], ("@b", "@c"): ["docs/y.md"], (): ["loose.txt"]}
    text = owners.render(routing, [])
    assert "@b or @c" in text and "**nobody**" in text


@needs_git
def test_cli_routes_the_files_of_a_real_branch_and_can_require_an_owner(tmp_path):
    repo = new_repo(tmp_path / "r", {".github/CODEOWNERS": "/src/ @a\n", "src/a.cs": "x\n"})
    git(repo, "switch", "-q", "-c", "feature")
    commit(repo, "feat: two areas", {"src/a.cs": "y\n", "docs/new.md": "z\n"})
    res = run_cli("owners", "--base", "main", "--head", "feature", cwd=repo, env={"GITHUB_STEP_SUMMARY": ""})
    assert res.returncode == 0 and "| @a | `src/a.cs` |" in res.stdout and "**nobody**" in res.stdout
    strict = run_cli("owners", "--base", "main", "--head", "feature", "--require-owner", cwd=repo, env={"GITHUB_STEP_SUMMARY": ""})
    assert strict.returncode == 1
