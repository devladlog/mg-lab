import json
import shutil

import pytest
import yaml

from dakit.findings import errors
from dakit.validate import validate_package, placeholders


def msgs(findings):
    return "\n".join(str(f) for f in findings)


def edit(path, fn):
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_real_package_is_clean(pkg):
    assert validate_package(pkg) == []


def test_source_package_still_has_placeholders(pkg):
    assert validate_package(pkg, strict=True)
    found = set()
    for f in pkg.glob("*.json"):
        found |= placeholders(f.read_text(encoding="utf-8"))
    assert found == {"APP_ID", "VENDOR_API_KEY_REGISTRATION_ID"}   # the only values that differ per environment


def test_versions_match_learn(pkg):
    app = json.loads((pkg / "manifest.json").read_text())
    agent = json.loads((pkg / "declarativeAgent.json").read_text())
    plugin = json.loads((pkg / "vendor-renewals-plugin.json").read_text())
    assert app["manifestVersion"] == "1.30" and agent["version"] == "v1.9" and plugin["schema_version"] == "v2.4"


def test_instructions_limit_and_blank(pkg):
    edit(pkg / "declarativeAgent.json", lambda d: d.update(instructions="x" * 8001))
    assert "8000" in msgs(errors(validate_package(pkg)))
    edit(pkg / "declarativeAgent.json", lambda d: d.update(instructions="   "))
    assert "instructions are required" in msgs(validate_package(pkg))


def test_duplicate_capability_and_unknown_property(pkg):
    edit(pkg / "declarativeAgent.json", lambda d: d.update(capabilities=[{"name": "WebSearch"}, {"name": "WebSearch"}], bogus=1))
    text = msgs(validate_package(pkg))
    assert "same capability twice" in text and "unknown property 'bogus'" in text


def test_too_many_starters(pkg):
    edit(pkg / "declarativeAgent.json", lambda d: d.update(conversation_starters=[{"text": f"q{i}"} for i in range(13)]))
    assert "conversation starters" in msgs(validate_package(pkg))


def test_function_must_match_an_operation_id(pkg):
    def rename(d):
        d["functions"][0]["name"] = "listRenewalz"
        d["runtimes"][0]["run_for_functions"][0] = "listRenewalz"
    edit(pkg / "vendor-renewals-plugin.json", rename)
    text = msgs(validate_package(pkg))
    assert "no operationId listRenewalz" in text
    assert "OpenAPI operation listRenewals is not exposed" in text


def test_run_for_functions_must_exist(pkg):
    edit(pkg / "vendor-renewals-plugin.json", lambda d: d["runtimes"][0]["run_for_functions"].append("ghost"))
    assert "ghost" in msgs(errors(validate_package(pkg)))


def test_missing_spec_and_card_files(pkg):
    (pkg / "openapi.yaml").unlink()
    assert "openapi.yaml is not in the package folder" in msgs(validate_package(pkg))


def test_missing_adaptive_card(pkg):
    (pkg / "adaptiveCards" / "renewal.json").unlink()
    assert "static_template file" in msgs(validate_package(pkg))


def test_card_must_be_an_adaptive_card(pkg):
    (pkg / "adaptiveCards" / "renewal.json").write_text('{"type": "Container"}')
    assert "not an Adaptive Card" in msgs(validate_package(pkg))


def test_write_function_without_confirmation_warns(pkg):
    def strip(d):
        del d["functions"][2]["capabilities"]["confirmation"]
        d["functions"][2]["capabilities"]["security_info"]["data_handling"] = ["GetPrivateData"]
    edit(pkg / "vendor-renewals-plugin.json", strip)
    text = msgs(validate_package(pkg))
    assert "without an AdaptiveCard confirmation" in text and "lacks ResourceStateUpdate" in text
    assert not errors(validate_package(pkg))   # warnings, not errors


def test_missing_security_info_warns(pkg):
    edit(pkg / "vendor-renewals-plugin.json", lambda d: d["functions"][1].update(capabilities={}))
    assert "cannot interact with other plugins" in msgs(validate_package(pkg))


def test_long_plugin_names_warn(pkg):
    edit(pkg / "vendor-renewals-plugin.json", lambda d: d.update(name_for_human="A very long plugin name over twenty"))
    assert "longer than 20" in msgs(validate_package(pkg))


def test_two_agents_in_one_package_are_refused(pkg):
    edit(pkg / "manifest.json", lambda d: d["copilotAgents"]["declarativeAgents"].append({"id": "second", "file": "declarativeAgent.json"}))
    assert "exactly one declarative agent" in msgs(validate_package(pkg))


def test_bad_app_manifest_is_caught_by_the_official_schema(pkg):
    edit(pkg / "manifest.json", lambda d: d.update(manifestVersion="1.19"))
    assert errors(validate_package(pkg))
    edit(pkg / "manifest.json", lambda d: d["name"].update(short="This short name is far too long to pass"))
    assert "manifest.json name" in msgs(validate_package(pkg))


def test_invalid_json_is_reported_not_raised(pkg):
    (pkg / "declarativeAgent.json").write_text("{ nope")
    assert "not valid JSON" in msgs(validate_package(pkg))
    (pkg / "manifest.json").unlink()
    assert "file not found" in msgs(validate_package(pkg))


def test_instructions_follow_learn_guidance():
    """Learn: define purpose, tool use, output format and failure behaviour; name the functions the OpenAPI defines."""
    from conftest import PACKAGE
    agent = json.loads((PACKAGE / "declarativeAgent.json").read_text())
    spec = yaml.safe_load((PACKAGE / "openapi.yaml").read_text())
    ids = [op["operationId"] for item in spec["paths"].values() for op in item.values()]
    for fn in ids:
        assert fn in agent["instructions"], f"instructions never mention {fn}"
    for section in ("# Purpose", "# Tools", "# Answer format"):
        assert section in agent["instructions"]
    assert len(agent["instructions"]) < 8000
