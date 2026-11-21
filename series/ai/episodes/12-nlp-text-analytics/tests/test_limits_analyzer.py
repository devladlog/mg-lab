import json

import pytest
from azure.core.exceptions import HttpResponseError

from conftest import ENDPOINT
from ticketnlp import limits
from ticketnlp.analyzer import Err
from ticketnlp.limits import MAX_CHARS, batched, split_text, text_records


def test_documented_limits_are_what_learn_says():
    assert limits.MAX_CHARS == 5120 and limits.RECORD_CHARS == 1000 and limits.F0_FREE_RECORDS_PER_MONTH == 5000
    assert limits.MAX_DOCS == {"language": 1000, "sentiment": 10, "key_phrases": 10, "entities": 5, "pii": 5}


@pytest.mark.parametrize("n,expected", [(0, 0), (1, 1), (1000, 1), (1001, 2), (5120, 6)])
def test_text_records_round_up_per_thousand_characters(n, expected):
    assert text_records("x" * n) == expected


def test_batched_preserves_order_and_size():
    assert [len(b) for b in batched(list(range(23)), 10)] == [10, 10, 3]
    assert list(batched([], 5)) == []


def test_short_text_is_one_chunk_and_blank_text_is_none():
    assert split_text("hello") == ["hello"] and split_text("  \n\n ") == []


def test_long_text_splits_on_paragraphs_first_and_every_chunk_fits():
    paras = [f"Paragraph {i}. " + "word " * 300 for i in range(8)]
    chunks = split_text("\n\n".join(paras))
    assert len(chunks) > 1 and all(len(c) <= MAX_CHARS for c in chunks)
    assert all(c.startswith("Paragraph") for c in chunks)                       # cut between paragraphs, not inside
    assert " ".join(" ".join(chunks).split()) == " ".join("\n\n".join(paras).split())


def test_one_huge_paragraph_splits_on_sentences():
    text = " ".join(f"Sentence number {i} is here." for i in range(400))
    chunks = split_text(text)
    assert len(chunks) >= 2 and all(len(c) <= MAX_CHARS for c in chunks) and all(c.endswith(".") for c in chunks)


def test_text_without_any_boundary_is_cut_hard_and_loses_nothing():
    text = "x" * 12000
    chunks = split_text(text)
    assert [len(c) for c in chunks] == [5120, 5120, 1760] and "".join(chunks) == text


def test_the_limit_counts_code_points_which_are_never_fewer_than_text_elements():
    text = "😡" * 6000                                                      # 6000 code points, 6000 text elements
    assert all(len(c) <= MAX_CHARS for c in split_text(text))
    family = "👨‍👩‍👧" * 3                                                       # 8 code points but 1 text element each: our count is the safe side
    assert len(family) == 15


def test_request_goes_to_analyze_text_with_the_entra_token_and_the_right_kind(analyzer, transport, cred):
    analyzer.sentiment([("a", "VPN drops again", "en")])
    req = transport.requests[0]
    body = json.loads(req.body)
    assert req.url.startswith(f"{ENDPOINT}/language/:analyze-text?api-version=") and req.method == "POST"
    assert req.headers["Authorization"] == "Bearer fake-entra-token"
    assert cred.scopes == ["https://cognitiveservices.azure.com/.default"]
    assert body["kind"] == "SentimentAnalysis" and body["parameters"]["opinionMining"] is True
    assert body["analysisInput"]["documents"] == [{"id": "a", "text": "VPN drops again", "language": "en"}]


@pytest.mark.parametrize("feature,method,n,requests_expected", [
    ("sentiment", "sentiment", 23, 3), ("key_phrases", "key_phrases", 11, 2), ("entities", "entities", 11, 3),
    ("pii", "pii", 6, 2), ("language", "languages", 1001, 2)])
def test_every_feature_is_batched_by_its_own_documented_limit(analyzer, service, feature, method, n, requests_expected):
    res = getattr(analyzer, method)([(str(i), f"ticket {i}", None) for i in range(n)])
    assert len(res) == n and not any(isinstance(v, Err) for v in res.values())
    assert analyzer.calls[feature] == requests_expected and len(service.calls) == requests_expected


def test_a_document_over_the_limit_never_leaves_the_machine_and_the_others_still_run(analyzer, service):
    res = analyzer.sentiment([("big", "x" * 5121, None), ("ok", "Thanks, great service", "en")])
    assert isinstance(res["big"], Err) and res["big"].code == "DocumentTooLong" and res["ok"].label == "positive"
    assert [d["id"] for c in service.calls for d in c["docs"]] == ["ok"]


def test_a_document_error_from_the_service_is_isolated_to_that_document(analyzer, service):
    service.fail_pii_for = {"b"}
    res = analyzer.pii([("a", "hello", "en"), ("b", "hello", "en")])
    assert res["a"].redacted == "hello" and isinstance(res["b"], Err) and res["b"].code == "InternalServerError"


def test_a_failed_request_raises_instead_of_returning_half_an_answer(analyzer, service):
    service.status_override = 500
    with pytest.raises(HttpResponseError):
        analyzer.key_phrases([("a", "hello", None)])


def test_opinion_mining_targets_come_back_as_aspects(analyzer):
    r = analyzer.sentiment([("a", "VPN drops, frustrating", "en")])["a"]
    assert r.aspects == [("VPN", "negative")] and r.scores["negative"] > .9
