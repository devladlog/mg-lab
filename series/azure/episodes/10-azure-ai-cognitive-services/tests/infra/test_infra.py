import json
import re
import subprocess

import pytest

from conftest import ROOT, resource


def test_bicep_lint_is_clean():
    r = subprocess.run(["bicep", "lint", str(ROOT / "infra" / "main.bicep")], capture_output=True, text=True)
    assert r.returncode == 0 and "Warning" not in r.stderr and "Error" not in r.stderr, r.stderr


def test_language_account_is_free_keyless_and_has_a_subdomain(main):
    acct = resource(main, "Microsoft.CognitiveServices/accounts")
    assert acct["kind"] == "TextAnalytics" and acct["sku"] == {"name": "F0"}
    props = acct["properties"]
    assert props["disableLocalAuth"] is True                       # Entra ID only
    assert props["customSubDomainName"] == "[parameters('accountName')]"   # Entra needs the custom subdomain


def test_role_is_language_reader_and_optional(main):
    ra = resource(main, "Microsoft.Authorization/roleAssignments")
    assert ra["condition"] == "[not(empty(parameters('principalId')))]" or "empty(parameters('principalId'))" in ra["condition"]
    assert main["variables"]["languageReaderRoleId"] == "7628b7b8-a8b2-4cdc-b46f-e9b35248918e"  # Learn: Cognitive Services Language Reader
    assert ra["properties"]["principalType"] == "[parameters('principalType')]"


def test_no_keys_or_secrets_in_outputs(main):
    assert set(main["outputs"]) == {"accountName", "endpoint", "location"}
    assert "listKeys" not in json.dumps(main)


def test_deploy_checks_the_one_free_resource_rule():
    text = (ROOT / "infra" / "deploy.sh").read_text()
    assert "kind=='TextAnalytics' && sku.name=='F0'" in text and "exit 1" in text


def test_teardown_deletes_then_purges():
    lines = [l for l in (ROOT / "infra" / "teardown.sh").read_text().splitlines() if l.startswith("az ")]
    assert lines[0].startswith("az group delete") and lines[1].startswith("az cognitiveservices account purge")


def test_rest_check_body_is_valid_json_for_language_detection():
    text = (ROOT / "infra" / "rest-check.sh").read_text()
    body = re.search(r"^BODY='(.*)'$", text, re.M).group(1)
    doc = json.loads(body)
    assert doc["kind"] == "LanguageDetection" and doc["analysisInput"]["documents"][0]["id"] == "1"
    assert "api-version=2023-04-01" in text and "cognitiveservices.azure.com" in text


@pytest.mark.parametrize("name", ["deploy.sh", "run.sh", "rest-check.sh", "teardown.sh"])
def test_shell_syntax(name):
    assert subprocess.run(["bash", "-n", str(ROOT / "infra" / name)]).returncode == 0


def test_no_key_or_secret_anywhere_in_the_source():
    files = list((ROOT / "src").rglob("*.cs")) + list((ROOT / "infra").glob("*"))
    for p in (f for f in files if not {"bin", "obj"} & set(f.parts)):
        t = p.read_text(errors="ignore")
        assert "AzureKeyCredential" not in t, p
        assert not re.search(r"[0-9a-f]{32}", t.replace("00000000000000000000000000000000", "")), p
