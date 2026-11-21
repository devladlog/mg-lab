import pytest

from aoai_gateway.errors import classify, classify_exception


def test_429_is_throttled_with_retry_after_seconds():
    d = classify(429, {"Retry-After": "7"})
    assert (d.kind, d.retry, d.retry_after_s) == ("throttled", True, 7.0)


def test_retry_after_ms_wins_over_seconds():
    assert classify(429, {"retry-after-ms": "1500", "retry-after": "2"}).retry_after_s == 1.5


def test_403_is_quota_exhausted_and_not_retried():
    d = classify(403, {})
    assert d.kind == "quota_exhausted" and d.retry is False


@pytest.mark.parametrize("body", [{"error": {"code": "content_filter", "message": "filtered"}},
                                  {"code": "content_filter", "message": "filtered"}])
def test_content_filter_is_never_retried_unchanged(body):
    d = classify(400, {}, body)
    assert d.kind == "content_filtered" and d.retry is False


def test_other_400_is_a_bad_request_with_its_code():
    d = classify(400, {}, {"error": {"code": "unsupported_parameter"}})
    assert d.kind == "bad_request" and "unsupported_parameter" in d.message


@pytest.mark.parametrize("status,kind,retry", [(503, "unavailable", True), (401, "auth", False),
                                               (404, "not_found", False), (500, "backend_error", True)])
def test_other_statuses(status, kind, retry):
    d = classify(status)
    assert (d.kind, d.retry) == (kind, retry)


def test_classify_exception_reads_status_headers_and_body():
    class FakeResponse:
        headers = {"retry-after": "3"}

    class FakeError(Exception):
        status_code = 429
        response = FakeResponse()
        body = None

    assert classify_exception(FakeError()).retry_after_s == 3.0
    assert classify_exception(ValueError("boom")).kind == "backend_error"
