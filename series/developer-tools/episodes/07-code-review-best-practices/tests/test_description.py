from __future__ import annotations

from conftest import DEMO, APP, run_cli
from review_kit import description


def names(body: str) -> list[str]:
    return [f.section for f in description.check(body)]


GOOD = (DEMO / "pr-body.good.md").read_text()
BAD = (DEMO / "pr-body.bad.md").read_text()


def test_the_description_of_the_demo_pull_request_passes():
    assert description.check(GOOD) == []


def test_placeholders_and_a_bare_checkbox_are_not_content():
    assert names(BAD) == list(description.REQUIRED)
    assert all("empty or a placeholder" in f.problem for f in description.check(BAD))


def test_a_missing_section_is_reported_as_missing():
    body = GOOD.replace("## Risk and rollback", "## Notes")
    [f] = description.check(body)
    assert (f.section, f.problem) == ("Risk and rollback", "section is missing")


def test_out_of_scope_is_optional():
    assert description.check(GOOD.split("## Out of scope")[0]) == []


def test_headings_are_case_insensitive_and_crlf_is_fine():
    assert description.check(GOOD.replace("## How to verify", "## how TO verify").replace("\n", "\r\n")) == []


def test_a_heading_inside_a_code_fence_is_not_a_section():
    body = "## What and why\n" + "x" * 30 + "\n```\n## How to verify\nrun the tests with enough words\n```\n"
    assert "How to verify" in names(body)


def test_html_comments_from_the_template_do_not_count_as_content():
    template = (APP / ".github" / "pull_request_template.md").read_text()
    assert names(template) == list(description.REQUIRED)


def test_the_template_has_exactly_the_sections_the_check_requires():
    template = description.sections((APP / ".github" / "pull_request_template.md").read_text())
    assert list(template) == [*description.REQUIRED, "Out of scope"]


def test_an_empty_body_fails_every_section():
    assert names("") == list(description.REQUIRED)


def test_cli_reads_stdin_and_the_exit_code_follows_the_result():
    ok = run_cli("description", "-", stdin=GOOD)
    assert ok.returncode == 0 and "description has" in ok.stdout
    bad = run_cli("description", "-", stdin=BAD, env={"GITHUB_STEP_SUMMARY": ""})
    assert bad.returncode == 1 and "Where to look: is empty or a placeholder" in bad.stdout
    assert run_cli("description", "-", stdin="", env={"GITHUB_STEP_SUMMARY": ""}).returncode == 1
