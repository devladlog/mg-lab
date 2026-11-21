import json

import azure.functions as func
import pytest
from conftest import EMPLOYEES, MANAGERS, principal
from openai import OpenAI

import function_app


def request(body, header=None):
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["X-MS-CLIENT-PRINCIPAL"] = header
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    return func.HttpRequest("POST", "/api/ask", body=data, headers=headers)


@pytest.fixture
def wired(monkeypatch, retriever, llm):
    monkeypatch.setattr(function_app, "get_deps", lambda: (retriever, llm))
    monkeypatch.setenv("CHAT_DEPLOYMENT", "chat")


def test_answers_an_employee(stub, wired):
    stub.reply = lambda m: "Up to 5 unused days can be carried over, to be taken by 31 March [1]."
    r = function_app.handle(request({"question": "Can I carry over leave days?"}, principal()))
    assert r.status_code == 200
    out = json.loads(r.get_body())
    assert set(out) == {"answer", "citations", "grounded", "sources_considered", "usage"}
    assert out["grounded"] and out["citations"][0]["n"] == 1


def test_no_principal_is_401_and_nothing_is_searched(stub, wired):
    r = function_app.handle(request({"question": "Can I carry over leave days?"}))
    assert r.status_code == 401
    assert stub.calls == []


def test_group_overage_is_403_with_an_actionable_message(stub, wired):
    hdr = principal(groups=(), extra=[{"typ": "_claim_names", "val": '{"groups":"src1"}'}])
    r = function_app.handle(request({"question": "x"}, hdr))
    assert r.status_code == 403 and "groups assigned to the application" in json.loads(r.get_body())["error"]
    assert stub.calls == []


def test_bad_json_is_400(wired):
    assert function_app.handle(request(b"question=hi", principal())).status_code == 400


def test_empty_question_is_400(wired):
    assert function_app.handle(request({"question": " "}, principal())).status_code == 400


def test_same_question_different_people_different_answers(stub, wired):
    stub.reply = lambda m: ("Band M2 is 66,000 to 82,000 EUR [1]." if "Band M2" in m[1]["content"]
                            else "I couldn't find this in the documents you have access to.")
    q = {"question": "What is the salary range for band M2?"}
    emp = json.loads(function_app.handle(request(q, principal(groups=(EMPLOYEES,)))).get_body())
    mgr = json.loads(function_app.handle(request(q, principal(groups=(EMPLOYEES, MANAGERS)))).get_body())
    assert emp["citations"] == [] and "couldn't find" in emp["answer"]
    assert "66,000" in mgr["answer"] and mgr["citations"][0]["title"].startswith("Contoso salary bands")


def test_rate_limit_becomes_503(stub, wired):
    stub.chat_status = 429
    r = function_app.handle(request({"question": "Can I carry over leave days?"}, principal()))
    assert r.status_code == 503


def test_content_filter_becomes_422(stub, wired):
    stub.chat_status = 400
    r = function_app.handle(request({"question": "Can I carry over leave days?"}, principal()))
    assert r.status_code == 422


def test_search_failure_becomes_503(stub, wired, monkeypatch):
    stub.search_status = 503
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    from copilot.retrieval import Retriever
    no_retry = Retriever(SearchClient(stub.endpoint, "hr-policies", AzureKeyCredential("stub"), retry_total=0))
    monkeypatch.setattr(function_app, "get_deps", lambda: (no_retry, OpenAI(base_url=f"{stub.endpoint}/openai/v1/",
                                                                              api_key="x", max_retries=0)))
    r = function_app.handle(request({"question": "Can I carry over leave days?"}, principal()))
    assert r.status_code == 503


def test_logs_never_contain_the_question(stub, wired, caplog):
    stub.reply = lambda m: "You get 25 days [1]."
    caplog.set_level("INFO", logger="copilot")
    function_app.handle(request({"question": "How many days of annual leave do I get?"}, principal()))
    assert caplog.records and all("annual leave" not in r.getMessage() for r in caplog.records)


def test_route_is_post_api_ask_and_anonymous_at_function_level():
    (fn,) = function_app.app.get_functions()
    b = fn.get_bindings_dict()["bindings"][0]
    assert b["route"] == "ask"
    assert str(getattr(b["authLevel"], "value", b["authLevel"])).lower() == "anonymous"
