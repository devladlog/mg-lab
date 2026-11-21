"""The custom connector definition must match what the function really does."""
import json
import re

import pytest
from conftest import ROOT, principal

SWAGGER = json.loads((ROOT / "connector" / "apiDefinition.swagger.json").read_text(encoding="utf-8"))
OP = SWAGGER["paths"]["/ask"]["post"]


def test_is_openapi_2_and_small_enough():
    # Custom connectors accept OpenAPI 2.0 only, and the file must be under 1 MB.
    assert SWAGGER["swagger"] == "2.0"
    assert (ROOT / "connector" / "apiDefinition.swagger.json").stat().st_size < 1_000_000
    assert SWAGGER["schemes"] == ["https"] and SWAGGER["basePath"] == "/api"


def test_one_operation_with_a_stable_id_and_a_description_the_agent_can_use():
    assert list(SWAGGER["paths"]) == ["/ask"] and list(SWAGGER["paths"]["/ask"]) == ["post"]
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", OP["operationId"])
    assert len(OP["description"]) > 80 and "permitted" in OP["description"]


def test_oauth2_is_the_first_and_only_security_definition():
    # "If there are multiple security definitions, the custom connector picks the top security definition."
    (name, sd), = SWAGGER["securityDefinitions"].items()
    assert sd["type"] == "oauth2" and sd["flow"] == "accessCode"
    assert SWAGGER["security"] == [{name: []}]


def test_every_response_code_the_function_returns_is_documented():
    import function_app
    src = (ROOT / "src" / "function_app.py").read_text(encoding="utf-8")
    codes = {int(c) for c in re.findall(r"_json\((\d{3}),", src)}
    assert codes == {int(c) for c in OP["responses"]}
    assert function_app is not None


def test_response_schema_matches_a_real_answer(stub, retriever, llm, monkeypatch):
    import azure.functions as func

    import function_app
    monkeypatch.setattr(function_app, "get_deps", lambda: (retriever, llm))
    stub.reply = lambda m: "You get 25 days [1]."
    r = function_app.handle(func.HttpRequest("POST", "/api/ask", body=b'{"question": "annual leave days?"}',
                                             headers={"X-MS-CLIENT-PRINCIPAL": principal(),
                                                      "Content-Type": "application/json"}))
    out = json.loads(r.get_body())
    schema = SWAGGER["definitions"]["AskResponse"]["properties"]
    assert set(out) == set(schema)
    assert set(out["citations"][0]) == set(schema["citations"]["items"]["properties"])


def test_request_schema_limits_match_the_code():
    q = SWAGGER["definitions"]["AskRequest"]["properties"]["question"]
    assert SWAGGER["definitions"]["AskRequest"]["required"] == ["question"] and q["maxLength"] == 1000


def test_no_real_hosts_or_ids():
    flat = json.dumps(SWAGGER)
    assert SWAGGER["host"].startswith("func-copilot-contoso.")
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", flat)


@pytest.mark.parametrize("field", ["answer", "grounded", "citations"])
def test_fields_have_friendly_names_for_makers(field):
    assert "x-ms-summary" in SWAGGER["definitions"]["AskResponse"]["properties"][field]
