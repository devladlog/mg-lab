from agent_ready import issue_lint as il


def codes(text):
    return {(f.level, f.code) for f in il.check_text(text)}


def test_ready_issue_has_no_findings(demo):
    assert il.check_file(demo / "issues/01-ready-loyalty-rounding.md") == []


def test_vague_issue_is_rejected(demo):
    found = codes((demo / "issues/02-vague-make-pricing-better.md").read_text())
    assert {("error", "problem"), ("error", "criteria"), ("warning", "hidden-text"), ("warning", "vague-words"), ("warning", "where")} <= found


def test_criteria_must_be_a_checklist():
    text = "# Rounding is wrong for halves\n\n## Problem\n" + "x" * 50 + "\n\n## Acceptance criteria\n- it works\n"
    assert ("error", "criteria") in codes(text)


def test_criteria_without_values_or_tests_warn():
    text = ("# Rounding is wrong for halves\n\n## Problem\n" + "The price is wrong when the discount lands on a half cent." + "\n\n"
            "## Acceptance criteria\n- [ ] it rounds correctly\n\n## Where to look\n- `src/a/b.cs`\n")
    c = codes(text)
    assert ("warning", "criteria-values") in c and ("warning", "criteria-tests") in c


def test_hidden_comment_text_is_not_counted_as_content():
    text = "# Rounding is wrong for halves\n\n<!--\n## Problem\n" + "y" * 80 + "\n-->\n"
    c = codes(text)
    assert ("warning", "hidden-text") in c and ("error", "problem") in c


def test_title_checks():
    assert ("error", "title") in codes("no heading here")
    assert ("warning", "title") in codes("# Fix\n\n## Problem\n" + "z" * 60)


def test_word_boundaries_do_not_misfire():
    # "betterment" and "setc" must not trigger "better" / "etc"
    text = ("# Rounding is wrong for halves\n\n## Problem\nBetterment of price setc is not the point; the half cent is wrong in LoyaltyPrice.\n\n"
            "## Acceptance criteria\n- [ ] 12.25 gives 11.03 and a test proves it\n\n## Where to look\n- `src/a/b.cs`\n")
    assert ("warning", "vague-words") not in codes(text)
