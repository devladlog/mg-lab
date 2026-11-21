import pytest
from conftest import ENDPOINT, FakePlatform
from aiplatform import endpoints, probe
from aiplatform.http import Api, COGNITIVE_SCOPE, ARM_SCOPE, Reply


# ---- endpoints -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", [ENDPOINT, ENDPOINT + "/", "contoso-ai.cognitiveservices.azure.com",
                                 "https://contoso-ai.openai.azure.com/", "https://contoso-ai.services.ai.azure.com"])
def test_all_three_fqdns_of_one_resource_give_the_same_name(url):
    assert endpoints.resource_name(url) == "contoso-ai"
    assert endpoints.tools_endpoint(url) == ENDPOINT


def test_all_endpoints_lists_the_three_fqdns():
    assert endpoints.all_endpoints(ENDPOINT) == {"tools": ENDPOINT, "openai": "https://contoso-ai.openai.azure.com", "foundry": "https://contoso-ai.services.ai.azure.com"}


@pytest.mark.parametrize("url", ["https://westeurope.api.cognitive.microsoft.com", "https://api.cognitive.microsofttranslator.com",
                                 "https://api.cognitive.microsoft.com"])
def test_regional_endpoints_are_refused_with_the_learn_reason(url):
    with pytest.raises(endpoints.EndpointError, match="custom subdomain"):
        endpoints.resource_name(url)


@pytest.mark.parametrize("url", ["http://contoso-ai.cognitiveservices.azure.com", "https://example.com", "https://a.b.cognitiveservices.azure.com", ""])
def test_other_hosts_and_http_are_refused(url):
    with pytest.raises(endpoints.EndpointError):
        endpoints.resource_name(url)


def test_resource_id_check():
    from conftest import RID
    assert endpoints.check_resource_id(RID + "/") == RID
    with pytest.raises(endpoints.EndpointError):
        endpoints.check_resource_id("/subscriptions/x/resourceGroups/r/providers/Microsoft.Storage/storageAccounts/s")


# ---- http layer ------------------------------------------------------------------------------------------------
def test_bearer_token_is_sent_and_no_key_header_ever(api, platform, cred):
    probe.run_probes(api, ENDPOINT)
    assert platform.calls
    for c in platform.calls:
        assert c["headers"]["authorization"] == "Bearer fake-entra-token"
        assert "ocp-apim-subscription-key" not in c["headers"] and "api-key" not in c["headers"]
    assert set(cred.scopes) == {COGNITIVE_SCOPE}


def test_arm_calls_use_the_management_scope(api, cred):
    from conftest import RID
    from aiplatform import audit
    audit.fetch(api, RID)
    assert set(cred.scopes) == {ARM_SCOPE}


def test_transport_error_has_no_status_and_is_reported_not_raised(cred):
    api = Api(cred, transport=FakePlatform(boom="/language"))
    r = api.call("POST", ENDPOINT + "/language/:analyze-text?api-version=2023-04-01", body={})
    assert r.status == 0 and "ConnectionError" in r.error


def test_reply_helpers():
    r = Reply(429, 5, {"error": {"code": "429", "message": "slow down"}}, "", {"Retry-After": "7", "X-RequestId": "abc"})
    assert r.retry_after == "7" and r.request_id == "abc" and "slow down" in r.error_code() and not r.ok


# ---- probes ----------------------------------------------------------------------------------------------------
def test_four_probes_hit_the_documented_routes(api, platform):
    res = probe.run_probes(api, ENDPOINT)
    assert [r.id for r in res] == ["language", "translator", "safety", "docintel"] and all(r.ok for r in res)
    paths = {(c["method"], c["path"]) for c in platform.calls}
    assert paths == {("POST", "/language/:analyze-text"), ("POST", "/translator/text/v3.0/translate"),
                     ("POST", "/contentsafety/text:analyze"), ("GET", "/documentintelligence/info")}
    assert {c["host"] for c in platform.calls} == {"contoso-ai.cognitiveservices.azure.com"}


def test_probe_details_are_read_from_the_responses(api):
    res = {r.id: r for r in probe.run_probes(api, ENDPOINT)}
    assert res["language"].detail == "pt (0.99)"
    assert "[pt]" in res["translator"].detail
    assert "Hate=0" in res["safety"].detail and "Violence=0" in res["safety"].detail
    assert res["docintel"].detail == "custom models 2 of 500"


def test_request_ids_are_captured_from_whichever_header_exists(api):
    res = {r.id: r for r in probe.run_probes(api, ENDPOINT)}
    assert res["language"].request_id and res["translator"].request_id == "tr-1"


def test_owner_without_a_data_role_gets_403_everywhere_with_the_learn_hint(cred):
    api = Api(cred, transport=FakePlatform(data_plane=False))
    res = probe.run_probes(api, ENDPOINT)
    assert [r.status for r in res] == [403] * 4 and all(r.verdict == "forbidden" for r in res)
    assert all("Cognitive Services User" in r.hint and "five minutes" in r.hint for r in res)
    assert "0 of 4" in probe.render(res)


def test_a_throttled_service_shows_retry_after_and_the_others_still_run(cred):
    api = Api(cred, transport=FakePlatform(throttle="translator"))
    res = {r.id: r for r in probe.run_probes(api, ENDPOINT)}
    assert res["translator"].verdict == "throttled" and "7 s" in res["translator"].hint
    assert res["language"].ok and res["safety"].ok


def test_no_retries_by_default_so_a_429_is_one_call(cred):
    t = FakePlatform(throttle="translator")
    probe.run_probes(Api(cred, transport=t), ENDPOINT, ["translator"])
    assert len(t.calls) == 1


def test_unreachable_is_a_verdict_not_a_crash(cred):
    res = probe.run_probes(Api(cred, transport=FakePlatform(boom="/contentsafety")), ENDPOINT, ["safety"])
    assert res[0].verdict == "unreachable" and res[0].status == 0 and "private" in res[0].hint


def test_docintel_errors_through_the_sdk_are_judged_like_the_rest(cred):
    res = probe.run_probes(Api(cred, transport=FakePlatform(data_plane=False)), ENDPOINT, ["docintel"])
    assert res[0].status == 403 and res[0].verdict == "forbidden" and res[0].request_id == "req-403"


def test_unexpected_200_shape_is_flagged(cred, monkeypatch):
    class Odd(FakePlatform):
        def send(self, request, **kw):
            r = super().send(request, **kw)
            return self._resp(request, 200, {"hello": "world"}) if "contentsafety" in request.url else r
    res = probe.run_probes(Api(cred, transport=Odd()), ENDPOINT, ["safety"])
    assert res[0].verdict == "unexpected-shape"


@pytest.mark.parametrize("status,verdict", [(401, "unauthorized"), (404, "not-found"), (500, "service-error"), (400, "client-error")])
def test_judge_table(status, verdict):
    assert probe.judge(status)[0] == verdict


def test_unknown_probe_name_is_an_error(api):
    with pytest.raises(ValueError, match="Unknown probe"):
        probe.run_probes(api, ENDPOINT, ["speech"])


def test_regional_endpoint_is_refused_before_any_call(api, platform):
    with pytest.raises(endpoints.EndpointError):
        probe.run_probes(api, "https://westeurope.api.cognitive.microsoft.com")
    assert platform.calls == []
