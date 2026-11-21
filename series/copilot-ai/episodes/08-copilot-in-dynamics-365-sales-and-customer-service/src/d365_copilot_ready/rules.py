"""Readiness rules. Every rule is tied to a statement on Microsoft Learn (see README References).

Severity: ``error`` = Learn says the section or the whole feature produces nothing for this record,
``warning`` = a documented part of the output will be missing or generic, ``info`` = worth knowing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Learn: "A case summary isn't generated if the descriptions added in the source case fields that Copilot uses
# are less than 38 words in English, without counting spaces."  (customer-service/use/copilot-use-summary)
CASE_SUMMARY_MIN_WORDS = 38

OPP_OPEN, OPP_WON, OPP_LOST = 0, 1, 2
KB_STATE_PUBLISHED = 3  # knowledgearticle statecode 3 = Published (statuscode 7)


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warning | info
    code: str
    entity: str
    record: str
    message: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "entity": self.entity,
                "record": self.record, "message": self.message}


class _Text(HTMLParser):
    """Collects visible text, and separately the text that sits inside tables, plus an image counter."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.table_parts: list[str] = []
        self.table_depth = 0
        self.images = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
        elif tag == "img":
            self.images += 1

    def handle_endtag(self, tag):
        if tag == "table" and self.table_depth:
            self.table_depth -= 1

    def handle_data(self, data):
        if data.strip():
            (self.table_parts if self.table_depth else self.parts).append(data)


def html_text(html: str | None) -> tuple[str, str, int]:
    """Return (text outside tables, text inside tables, image count) for an HTML fragment."""
    p = _Text()
    p.feed(html or "")
    p.close()
    norm = lambda parts: " ".join(" ".join(parts).split())
    return norm(p.parts), norm(p.table_parts), p.images


def count_words(*texts: str | None) -> int:
    return sum(len(re.findall(r"\S+", t or "")) for t in texts)


def _name(rec: dict, *keys: str) -> str:
    for k in keys:
        if rec.get(k):
            return str(rec[k])
    return "(no name)"


# ---------------------------------------------------------------- Sales

def check_opportunity(opp: dict, n_products: int, n_quotes: int) -> list[Finding]:
    """Attributes behind the opportunity summary (sales/understand-copilot-summaries)."""
    rec = _name(opp, "name")
    out: list[Finding] = []

    def f(sev, code, msg):
        out.append(Finding(sev, code, "opportunity", rec, msg))

    state = opp.get("statecode", OPP_OPEN)
    if state == OPP_OPEN:
        if opp.get("estimatedvalue") is None:
            f("warning", "O001", "estimatedvalue is empty: 'Est. revenue' is missing from the basic information")
        if not opp.get("estimatedclosedate"):
            f("warning", "O002", "estimatedclosedate is empty: 'Est. close date' is missing from the basic information")
    else:
        if opp.get("actualvalue") is None:
            f("warning", "O001", "actualvalue is empty on a closed opportunity: 'Actual revenue' is missing")
        if not opp.get("actualclosedate"):
            f("warning", "O002", "actualclosedate is empty on a closed opportunity: 'Actual close date' is missing")
    if not opp.get("_parentcontactid_value"):
        f("warning", "O003", "parentcontactid is empty: no key contact, and the quote statement drops the contact name")
    if not opp.get("_parentaccountid_value"):
        f("error", "O004", "parentaccountid is empty: no account history and no purchase history, they are built from the parent account")
    if n_products == 0:
        f("warning", "O005", "no opportunity products: the product section has nothing to describe")
    elif opp.get("budgetamount") is None:
        f("info", "O006", "products exist but budgetamount is empty: the budget sentence of the product section is incomplete")
    if n_quotes == 0 and state == OPP_OPEN:
        f("info", "O007", "no quotes linked to the opportunity: the quote section stays out of the summary")
    return out


def check_account(acc: dict, n_closed_opportunities: int) -> list[Finding]:
    """Account history sentence uses createdon, industrycode and the closed opportunities of the account."""
    rec = _name(acc, "name")
    out: list[Finding] = []
    if acc.get("industrycode") is None:
        out.append(Finding("warning", "A001", "account", rec,
                           "industrycode is empty: the 'operates in the ... industry sector' sentence cannot be completed"))
    if n_closed_opportunities == 0:
        out.append(Finding("info", "A002", "account", rec,
                           "no closed opportunities: Copilot uses the 'customer since' variant and has no purchase history"))
    return out


# ---------------------------------------------------------------- Customer Service

def case_words(case: dict, notes: list[str], emails: list[str]) -> int:
    """Words in the text fields the case summary is built from."""
    mails = (html_text(e)[0] for e in emails)
    return count_words(case.get("title"), case.get("description"), *notes, *mails)


def check_case(case: dict, notes: list[str], emails: list[str]) -> list[Finding]:
    """Default case summary fields (customer-service/administer/copilot-map-custom-fields) and the word minimum."""
    rec = case.get("ticketnumber") or _name(case, "title")
    out: list[Finding] = []

    def f(sev, code, msg):
        out.append(Finding(sev, code, "case", rec, msg))

    words = case_words(case, notes, emails)
    if words < CASE_SUMMARY_MIN_WORDS:
        f("error", "C001", f"only {words} words across title, description, notes and emails: Learn says no summary is "
                           f"generated below {CASE_SUMMARY_MIN_WORDS} words in English")
    elif count_words(case.get("description")) < CASE_SUMMARY_MIN_WORDS and not notes and not emails:
        f("info", "C002", "description alone is short and there are no notes or emails to add context")
    if not case.get("_customerid_value"):
        f("warning", "C003", "customer is empty: the summary has no customer to refer to")
    if not case.get("_productid_value"):
        f("warning", "C004", "product is empty: the Product field is a default summary input (reps also need prvReadProduct)")
    if not case.get("_subjectid_value"):
        f("info", "C005", "subject is empty: the Subject field is a default summary input")
    if case.get("casetypecode") is None:
        f("info", "C006", "case type is empty: the Case Type field is a default summary input")
    return out


def is_usable(art: dict, ui_localeid: int, locale_of: dict[str, int]) -> bool:
    """Usable by Ask a question: see the rules table in the README."""
    outside, _inside, _images = html_text(art.get("content"))
    return (art.get("statecode") == KB_STATE_PUBLISHED
            and bool(art.get("islatestversion"))
            and locale_of.get(art.get("_languagelocaleid_value")) == ui_localeid
            and bool(outside))


def check_article(art: dict, ui_localeid: int, locale_of: dict[str, int]) -> list[Finding]:
    """What Copilot 'Ask a question' can use (contact-center/administer/copilot-enable-help-pane)."""
    rec = _name(art, "title")
    code_pub = art.get("articlepublicnumber")
    if code_pub:
        rec = f"{code_pub} {rec}"
    out: list[Finding] = []

    def f(sev, code, msg):
        out.append(Finding(sev, code, "knowledgearticle", rec, msg))

    if art.get("statecode") != KB_STATE_PUBLISHED:
        f("error", "K001", "state is not Published: Copilot only uses published articles")
    if not art.get("islatestversion"):
        f("error", "K002", "not the latest version: Copilot only uses the latest version of an article")
    lang = locale_of.get(art.get("_languagelocaleid_value") or "")
    if lang is None:
        f("warning", "K003", "language not resolved: Copilot only uses articles tagged with the UI language")
    elif lang != ui_localeid:
        f("error", "K003", f"language {lang} differs from the UI language {ui_localeid}: not used for that UI language")
    outside, inside, images = html_text(art.get("content"))
    if not outside and not inside:
        f("error", "K004", "content is empty: Copilot reads the content column only, not title, keywords or description")
    elif not outside and inside:
        f("error", "K005", "all text is inside tables: Learn says Copilot can't read tables")
    elif inside:
        f("warning", "K005", "part of the text is inside a table: Learn says Copilot can't read tables")
    if images:
        f("info", "K006", f"{images} image(s): Learn says Copilot can't read images, make sure the text carries the answer")
    return out
