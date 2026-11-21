import pytest

from repo_guard.commit_rules import MAX_HEADER, check_message


@pytest.mark.parametrize("message", [
    "feat: add paging to the orders endpoint",
    "fix(api): handle an empty export file",
    "docs(readme): explain the hook setup",
    "refactor(orders/export): split the writer",
    "feat(api)!: drop the v1 orders endpoint",
    "fix: trim names\n\nCustomers pasted names with trailing spaces.",
    "Merge branch 'main' into feature/orders-paging",
    'Revert "feat: add paging to the orders endpoint"',
    "fixup! feat: add paging to the orders endpoint",
])
def test_valid_messages(message):
    assert check_message(message).ok, check_message(message).errors


@pytest.mark.parametrize("message, expected", [
    ("Updated stuff", "header must look like"),
    ("feat:add paging", "header must look like"),          # no space after the colon
    ("Feat: add paging", "header must look like"),         # types are lower case
    ("feature: add paging", "unknown type 'feature'"),
    ("fix: handle empty files.", "must not end with a period"),
    ("fix: trim names\nbody right under the header", "blank line"),
    ("", "empty commit message"),
])
def test_invalid_messages(message, expected):
    result = check_message(message)
    assert not result.ok
    assert any(expected in e for e in result.errors), result.errors


def test_header_length_limit():
    subject = "x" * (MAX_HEADER - len("feat: "))
    assert check_message(f"feat: {subject}").ok
    result = check_message(f"feat: {subject}y")
    assert not result.ok and "keep it to 72" in result.errors[0]


def test_comments_and_scissors_are_ignored():
    message = (
        "# Please enter the commit message for your changes.\n"
        "fix(ui): keep focus after save\n"
        "\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x b/x\n"
    )
    assert check_message(message).ok


def test_breaking_change_detected_from_bang_and_footer():
    assert check_message("feat(api)!: drop v1").breaking
    footer = "feat(api): new paging\n\nUses cursors.\n\nBREAKING CHANGE: page numbers are gone"
    result = check_message(footer)
    assert result.ok and result.breaking and result.scope == "api"


def test_windows_line_endings_are_accepted():
    assert check_message("fix: trim names\r\n\r\nBody line.\r\n").ok
