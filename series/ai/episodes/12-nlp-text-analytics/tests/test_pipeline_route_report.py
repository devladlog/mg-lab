import json

from conftest import FakeService
from ticketnlp import backstop, cost
from ticketnlp.pipeline import MIN_LANGUAGE_CONFIDENCE, Analysis, merge_sentiment, process
from ticketnlp.report import build_report
from ticketnlp.route import route

BAD = ("Third day in a row the VPN drops every ten minutes, really frustrating. Call Alex Demo on +351 912 345 678 "
       "or write to alex.demo@contoso.com.")


def sent_to_analytics(service):
    """Everything the three analytics features received."""
    return [d["text"] for c in service.calls if c["kind"] in ("SentimentAnalysis", "KeyPhraseExtraction", "EntityRecognition") for d in c["docs"]]


def test_analytics_only_ever_see_redacted_text(analyzer, service):
    [a] = process(analyzer, [("t1", BAD)])
    seen = " ".join(sent_to_analytics(service))
    for secret in ("Alex Demo", "912 345 678", "alex.demo@contoso.com"):
        assert secret not in seen
    assert "VPN drops" in seen and a.pii_categories == {"Person": 1, "Email": 1, "PhoneNumber": 1}
    assert "Alex Demo" not in a.redacted_text and a.sentiment == "negative"


def test_the_order_is_language_then_pii_then_the_three_analytics(analyzer, service):
    process(analyzer, [("t1", BAD)])
    assert [c["kind"] for c in service.calls] == ["LanguageDetection", "PiiEntityRecognition", "SentimentAnalysis", "KeyPhraseExtraction", "EntityRecognition"]


def test_the_detected_language_is_passed_on_to_every_later_call(analyzer, service):
    process(analyzer, [("pt", "O Outlook não abre desde ontem. Obrigada, Taylor Demo.")])
    langs = {c["kind"]: {d["language"] for d in c["docs"]} for c in service.calls if c["kind"] != "LanguageDetection"}
    assert langs == {"PiiEntityRecognition": {"pt"}, "SentimentAnalysis": {"pt"}, "KeyPhraseExtraction": {"pt"}, "EntityRecognition": {"pt"}}


def test_an_uncertain_language_is_flagged_and_not_forced(analyzer, service):
    [a] = process(analyzer, [("x", "Hello team, o VPN voltou a falhar hoje de manhã. Thanks!")])
    assert a.language_uncertain and a.language_confidence < MIN_LANGUAGE_CONFIDENCE
    assert route(a)[0] == "manual-review" and "uncertain" in route(a)[1][0]
    later = [d["language"] for c in service.calls[1:] for d in c["docs"]]
    assert all(lang == "en" for lang in later)          # the SDK/service default: None means English, which is why we flag it


def test_the_local_backstop_catches_what_the_service_cannot_know(analyzer, service):
    [a] = process(analyzer, [("badge", "My badge CON-48213 stopped opening the door in Porto.")])
    assert a.backstop_hits == ["EmployeeId"] and "[EmployeeId]" in a.redacted_text
    assert "CON-48213" not in " ".join(sent_to_analytics(service))


def test_a_long_ticket_is_chunked_analysed_per_chunk_and_merged(analyzer, service):
    text = "From Alex Demo: " + "The printer jams again and it is frustrating. " * 140
    [a] = process(analyzer, [("long", text)])
    assert a.chunks == 2 and a.sentiment == "negative" and a.key_phrases.count("printer") == 1       # de-duplicated
    pii_docs = [d for c in service.calls if c["kind"] == "PiiEntityRecognition" for d in c["docs"]]
    assert [d["id"] for d in pii_docs] == ["long#0", "long#1"] and all(len(d["text"]) <= 5120 for d in pii_docs)
    assert a.pii_categories == {"Person": 1}


def test_blank_text_is_skipped_without_any_request(analyzer, service):
    [a] = process(analyzer, [("b", "   \n ")])
    assert a.skipped == "empty text" and service.calls == []


def test_redaction_failure_fails_closed_nothing_else_runs_on_that_raw_text(analyzer, service):
    service.fail_pii_for = {"bad#0"}
    ok, bad = process(analyzer, [("ok", "Thanks, great service from Sam Demo"), ("bad", BAD)])
    assert bad.skipped.startswith("blocked") and bad.sentiment is None and bad.redacted_text == "" and "pii: InternalServerError" in bad.errors
    assert ok.sentiment == "positive"
    assert "Alex Demo" not in " ".join(sent_to_analytics(service)) and "drops every ten" not in " ".join(sent_to_analytics(service))
    assert route(bad)[0] == "manual-review"


def test_raw_mode_exists_only_to_show_the_leak_and_never_keeps_the_text(analyzer, service):
    [a] = process(analyzer, [("t1", BAD)], redact=False)
    assert a.redacted_text == "" and "Alex Demo" in " ".join(a.key_phrases)
    assert not any(c["kind"] == "PiiEntityRecognition" for c in service.calls)


def test_merge_sentiment_is_length_weighted_and_mixed_when_chunks_disagree():
    pos = {"positive": 1.0, "neutral": 0.0, "negative": 0.0}
    neg = {"positive": 0.0, "neutral": 0.0, "negative": 1.0}
    assert merge_sentiment([(100, "negative", neg), (300, "negative", neg)])[0] == "negative"
    label, scores = merge_sentiment([(100, "positive", pos), (300, "negative", neg)])
    assert label == "mixed" and abs(scores["negative"] - 0.75) < 1e-9


def test_backstop_is_case_insensitive_and_counts_each_hit():
    out, hits = backstop.redact("con-12345 and CON-99999, but not CON-1234")
    assert out == "[EmployeeId] and [EmployeeId], but not CON-1234" and hits == ["EmployeeId", "EmployeeId"]


def mk(**kw):
    base = dict(id="x", language="en", language_confidence=.99, sentiment="neutral", sentiment_scores={"positive": .1, "neutral": .8, "negative": .1})
    base.update(kw)
    return Analysis(**base)


def test_routing_rules_apply_in_a_fixed_order_with_a_reason():
    assert route(mk(skipped="empty text"))[0] == "manual-review"
    assert route(mk(errors=["sentiment: X"]))[0] == "manual-review"
    assert route(mk(language="es"))[0] == "translate-first"
    neg = {"positive": .0, "neutral": .1, "negative": .9}
    assert route(mk(sentiment="negative", sentiment_scores=neg)) == ("priority-review", ["negative 0.90 >= 0.85"])
    assert route(mk(sentiment="negative", sentiment_scores={"positive": 0, "neutral": .3, "negative": .7}))[0] == "standard"
    assert route(mk(sentiment="positive"))[0] == "feedback-log"
    assert route(mk(language="es", sentiment="negative", sentiment_scores=neg))[0] == "translate-first"       # language beats escalation


def test_report_has_aggregates_and_no_ticket_text_or_pii(analyzer):
    res = process(analyzer, [("a", BAD), ("b", "Thanks, great service from Sam Demo"), ("c", "   ")])
    md = build_report(res, analyzer.calls, cost.estimate([BAD, "x", ""]))
    assert "3 tickets" in md and "priority-review" in md and "Not analysed or partly failed" in md and "c" in md.split("partly failed")[1]
    for secret in ("Alex Demo", "alex.demo@contoso.com", "912 345 678", "Sam Demo"):
        assert secret not in md
    assert "Person" in md and "vpn" in md


def test_cost_estimate_counts_chunks_and_each_feature():
    est = cost.estimate(["x" * 1200, "y" * 6000, ""])
    # ticket 1: 1 chunk of 1200 -> 2 records; ticket 2: chunks of 5120 and 880 -> 6 + 1 records, language only on the first (6)
    assert est["language"] == 2 + 6 and est["pii"] == est["sentiment"] == est["key_phrases"] == est["entities"] == 2 + 7
    assert est["total"] == 8 + 4 * 9
    assert round(cost.months_of_free_tier(est["total"], 100), 2) == round(44 * 100 / 5000, 2)
