import copy

import pytest
import yaml

from dakit.openapi_lint import lint_openapi
from conftest import PACKAGE


def base():
    return yaml.safe_load((PACKAGE / "openapi.yaml").read_text())


def lint(tmp_path, spec):
    p = tmp_path / "spec.yaml"
    p.write_text(yaml.safe_dump(spec, sort_keys=False))
    return "\n".join(str(f) for f in lint_openapi(p))


def test_real_spec_is_clean():
    assert lint_openapi(PACKAGE / "openapi.yaml") == []


def test_not_openapi(tmp_path):
    assert "not a valid OpenAPI description" in lint(tmp_path, {"openapi": "3.0.3", "info": {"title": "x"}})


def test_unreadable(tmp_path):
    out = lint_openapi(tmp_path / "missing.yaml")
    assert out and "cannot read" in out[0].message


def test_missing_info_description_and_servers(tmp_path):
    s = base(); del s["info"]["description"]; del s["servers"]
    text = lint(tmp_path, s)
    assert "info.description" in text and "no server URL" in text


def test_http_server_warns(tmp_path):
    s = base(); s["servers"] = [{"url": "http://insecure.example"}]
    assert "WARNING servers" in lint(tmp_path, s)


def test_operation_rules(tmp_path):
    s = base()
    op = s["paths"]["/renewals"]["get"]
    del op["operationId"]; del op["description"]; op["parameters"][0].pop("description")
    text = lint(tmp_path, s)
    assert "no operationId" in text and "only a summary" in text and "parameter withinDays" in text


def test_duplicate_operation_ids(tmp_path):
    s = base(); s["paths"]["/vendors/{vendorId}"]["get"]["operationId"] = "listRenewals"
    assert "is not unique" in lint(tmp_path, s)   # openapi-spec-validator already refuses it


def test_no_error_response_warns(tmp_path):
    s = base(); s["paths"]["/renewals"]["get"]["responses"] = {"200": s["paths"]["/renewals"]["get"]["responses"]["200"]}
    assert "no error response documented" in lint(tmp_path, s)


@pytest.mark.parametrize("keyword", ["oneOf", "anyOf", "allOf"])
def test_polymorphism_is_flagged(tmp_path, keyword):
    s = base()
    s["components"]["schemas"]["Reminder"]["properties"]["note"] = {keyword: [{"type": "string"}, {"type": "integer"}]}
    assert f"{keyword} is not supported" in lint(tmp_path, s)


def test_circular_reference_is_flagged(tmp_path):
    s = base()
    s["components"]["schemas"]["Renewal"]["properties"]["parent"] = {"$ref": "#/components/schemas/Renewal"}
    assert "circular reference" in lint(tmp_path, s)


def test_nested_object_in_request_body_is_flagged(tmp_path):
    s = base()
    s["components"]["schemas"]["ReminderRequest"]["properties"]["target"] = {"type": "object", "properties": {"id": {"type": "string"}}}
    assert "nested objects in request bodies" in lint(tmp_path, s)


def test_nested_object_in_parameter_is_flagged(tmp_path):
    s = base()
    s["paths"]["/renewals"]["get"]["parameters"][1]["schema"] = {"type": "object", "properties": {"inner": {"type": "object"}}}
    assert "nested objects in parameters" in lint(tmp_path, s)


def test_array_of_scalars_is_fine(tmp_path):
    s = base()
    s["components"]["schemas"]["ReminderRequest"]["properties"]["tags"] = {"type": "array", "items": {"type": "string"}}
    assert lint(tmp_path, s) == ""


def test_security_scheme_rules(tmp_path):
    s = base()
    s["components"]["securitySchemes"] = {
        "Cookie": {"type": "apiKey", "in": "cookie", "name": "sid"},
        "Header": {"type": "apiKey", "in": "header", "name": "X-API-KEY"},
        "Oauth": {"type": "oauth2", "flows": {"implicit": {"authorizationUrl": "https://a.example/auth", "scopes": {}}}},
    }
    text = lint(tmp_path, s)
    assert "API keys in cookies" in text
    assert "prefer http bearer" in text
    assert "OAuth flow implicit" in text
