from d365_copilot_ready import rules
from d365_copilot_ready.rules import (case_words, check_account, check_article, check_case, check_opportunity,
                                       count_words, html_text, is_usable)

EN, PT = "L-EN", "L-PT"
LOCALES = {EN: 1033, PT: 2070}


def codes(findings):
    return sorted(f.code for f in findings)


def opp(**kw):
    base = dict(name="o", statecode=0, estimatedvalue=1, estimatedclosedate="2026-12-01",
                _parentcontactid_value="c", _parentaccountid_value="a", budgetamount=1)
    base.update(kw)
    return base


def test_open_opportunity_complete_has_no_findings():
    assert check_opportunity(opp(), n_products=1, n_quotes=1) == []


def test_open_opportunity_uses_estimated_fields_closed_uses_actual_fields():
    f = check_opportunity(opp(estimatedvalue=None, estimatedclosedate=None), 1, 1)
    assert codes(f) == ["O001", "O002"]
    assert "estimatedvalue" in f[0].message
    closed = check_opportunity(opp(statecode=1, estimatedvalue=None, estimatedclosedate=None,
                                   actualvalue=None, actualclosedate=None), 1, 1)
    assert codes(closed) == ["O001", "O002"]
    assert "actualvalue" in closed[0].message
    # a closed opportunity does not need an estimated value
    assert check_opportunity(opp(statecode=1, estimatedvalue=None, actualvalue=5, actualclosedate="2025-01-01"), 1, 1) == []


def test_missing_parent_account_is_an_error_missing_contact_a_warning():
    f = {x.code: x.severity for x in check_opportunity(opp(_parentaccountid_value=None, _parentcontactid_value=None), 1, 1)}
    assert f == {"O003": "warning", "O004": "error"}


def test_products_and_quotes_rules():
    assert codes(check_opportunity(opp(), 0, 0)) == ["O005", "O007"]
    assert codes(check_opportunity(opp(budgetamount=None), 2, 1)) == ["O006"]
    # no quote is only worth a note on open opportunities
    assert codes(check_opportunity(opp(statecode=1, actualvalue=1, actualclosedate="x"), 1, 0)) == []


def test_account_rules():
    assert codes(check_account({"name": "a", "industrycode": None}, 0)) == ["A001", "A002"]
    assert check_account({"name": "a", "industrycode": 3}, 2) == []


def test_count_words_and_html_text():
    assert count_words("one two", None, " three ") == 3
    outside, inside, images = html_text("<p>Hello <b>world</b></p><table><tr><td>cell</td></tr></table><img src='x'>")
    assert outside == "Hello world" and inside == "cell" and images == 1


def test_case_word_minimum_is_38_words():
    just_under = " ".join(["w"] * 37)
    exactly = " ".join(["w"] * 38)
    assert codes(check_case({"ticketnumber": "T", "description": just_under, "_customerid_value": "c",
                             "_productid_value": "p", "_subjectid_value": "s", "casetypecode": 1}, [], [])) == ["C001"]
    assert check_case({"ticketnumber": "T", "description": exactly, "_customerid_value": "c",
                       "_productid_value": "p", "_subjectid_value": "s", "casetypecode": 1}, [], []) == []


def test_case_words_come_from_notes_and_email_text_not_markup():
    base = {"ticketnumber": "T", "title": "t", "description": "short", "_customerid_value": "c",
            "_productid_value": "p", "_subjectid_value": "s", "casetypecode": 1}
    mail = "<p>" + " ".join(["word"] * 40) + "</p>"
    assert check_case(base, [], [mail]) == []
    # 40 tags without text must not count as words
    assert codes(check_case(base, [], ["<br/>" * 40])) == ["C001"]
    assert check_case(base, [" ".join(["n"] * 40)], []) == []


def test_case_missing_default_fields():
    long_text = " ".join(["w"] * 50)
    f = check_case({"ticketnumber": "T", "description": long_text}, [], [])
    assert codes(f) == ["C003", "C004", "C005", "C006"]


def art(**kw):
    base = dict(title="t", articlepublicnumber="KA-1", content="<p>text</p>", statecode=3,
                islatestversion=True, _languagelocaleid_value=EN)
    base.update(kw)
    return base


def test_article_ok():
    assert check_article(art(), 1033, LOCALES) == []


def test_article_state_version_language():
    assert codes(check_article(art(statecode=0), 1033, LOCALES)) == ["K001"]
    assert codes(check_article(art(statecode=4), 1033, LOCALES)) == ["K001"]
    assert codes(check_article(art(islatestversion=False), 1033, LOCALES)) == ["K002"]
    assert codes(check_article(art(_languagelocaleid_value=PT), 1033, LOCALES)) == ["K003"]
    assert check_article(art(_languagelocaleid_value=PT), 2070, LOCALES) == []
    f = check_article(art(_languagelocaleid_value="unknown"), 1033, LOCALES)
    assert [(x.code, x.severity) for x in f] == [("K003", "warning")]


def test_article_content_column_only():
    # title and keywords do not help: content is what Copilot reads
    assert codes(check_article(art(content=""), 1033, LOCALES)) == ["K004"]
    assert codes(check_article(art(content=None), 1033, LOCALES)) == ["K004"]
    assert codes(check_article(art(content="<p> </p>"), 1033, LOCALES)) == ["K004"]


def test_article_tables_and_images():
    only_table = "<table><tr><td>a</td></tr></table>"
    f = check_article(art(content=only_table), 1033, LOCALES)
    assert [(x.code, x.severity) for x in f] == [("K005", "error")]
    mixed = "<p>intro</p>" + only_table + "<img src='x'/><img src='y'/>"
    f = check_article(art(content=mixed), 1033, LOCALES)
    assert [(x.code, x.severity) for x in f] == [("K005", "warning"), ("K006", "info")]
    assert "2 image" in f[1].message


def test_constants_match_learn():
    assert rules.CASE_SUMMARY_MIN_WORDS == 38
    assert rules.KB_STATE_PUBLISHED == 3
    assert (rules.OPP_OPEN, rules.OPP_WON, rules.OPP_LOST) == (0, 1, 2)


def test_case_words_helper_and_is_usable_agree_with_the_checks():
    assert case_words({"title": "a b", "description": "c"}, ["d e"], ["<p>f</p>"]) == 6
    ok = art()
    assert is_usable(ok, 1033, LOCALES) and not is_usable(ok, 2070, LOCALES)
    assert not is_usable(art(statecode=0), 1033, LOCALES)
    assert not is_usable(art(islatestversion=False), 1033, LOCALES)
    assert not is_usable(art(content="<table><tr><td>x</td></tr></table>"), 1033, LOCALES)
    assert not is_usable(art(_languagelocaleid_value="unknown"), 1033, LOCALES)
    # an article with no error finding is usable and the other way round
    for a in (art(), art(statecode=0), art(content=""), art(_languagelocaleid_value=PT)):
        no_error = not [f for f in check_article(a, 1033, LOCALES) if f.severity == "error"]
        assert is_usable(a, 1033, LOCALES) == no_error
