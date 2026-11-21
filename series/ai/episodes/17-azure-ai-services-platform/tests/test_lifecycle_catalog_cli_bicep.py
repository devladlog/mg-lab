import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from aiplatform import catalog, cli, lifecycle

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 21)


def write(tmp, rel, text):
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---- register --------------------------------------------------------------------------------------------------
def test_register_is_well_formed_and_every_source_is_a_learn_page():
    reg = lifecycle.load_register()
    assert len(reg) >= 9 and len({e.id for e in reg}) == len(reg)
    for e in reg:
        assert e.url.startswith("https://learn.microsoft.com/") and e.patterns and e.retires.year >= 2025


def test_the_dates_we_cite():
    d = {e.id: e.retires.isoformat() for e in lifecycle.load_register()}
    assert d["image-analysis"] == "2028-09-25" and d["custom-vision"] == "2028-09-25"
    assert d["language-sentiment"] == d["language-key-phrases"] == d["language-clu-cqa"] == "2029-03-31"
    assert d["content-moderator"] == "2027-03-15" and d["anomaly-metrics-personalizer"] == "2026-10-01"


# ---- scanner ---------------------------------------------------------------------------------------------------
def test_finds_each_retiring_call_with_file_and_line(tmp_path):
    write(tmp_path, "a/app.py", "import x\nr = client.analyze_sentiment(docs, show_opinion_mining=True)\nk = client.extract_key_phrases(docs)\n")
    write(tmp_path, "b/vision.py", "from azure.ai.vision.imageanalysis import ImageAnalysisClient\n")
    rows = lifecycle.summarise(lifecycle.scan(tmp_path), TODAY)
    assert [r["entry"].id for r in rows] == ["image-analysis", "language-sentiment", "language-key-phrases"]      # soonest first
    sent = rows[1]["hits"][0]
    assert (sent.path, sent.line) == ("a/app.py", 2)


def test_supported_language_features_are_not_flagged(tmp_path):
    write(tmp_path, "ok.py", "client.detect_language(docs)\nclient.recognize_pii_entities(docs)\nclient.recognize_entities(docs)\n")
    assert lifecycle.scan(tmp_path) == []


def test_tests_docs_and_venvs_are_skipped_unless_asked(tmp_path):
    write(tmp_path, "tests/test_x.py", "client.analyze_sentiment(d)\n")
    write(tmp_path, ".venv/lib/x.py", "client.analyze_sentiment(d)\n")
    write(tmp_path, "README.md", "analyze_sentiment\n")
    write(tmp_path, "script.yaml", "narration: analyze_sentiment\n")
    assert lifecycle.scan(tmp_path) == []
    assert len(lifecycle.scan(tmp_path, include_tests=True)) == 1


def test_bicep_and_json_are_scanned_too(tmp_path):
    write(tmp_path, "main.bicep", "// uses ContentModeratorClient somewhere\n")
    write(tmp_path, "cfg.json", '{"kind": "SentimentAnalysis"}\n')
    ids = {h.entry.id for h in lifecycle.scan(tmp_path)}
    assert ids == {"content-moderator", "language-sentiment"}


def test_a_single_file_can_be_scanned(tmp_path):
    f = write(tmp_path, "one.py", "x = CustomVisionPredictionClient\n")
    assert [h.entry.id for h in lifecycle.scan(f)] == ["custom-vision"]


@pytest.mark.parametrize("d,status", [("2026-10-01", "RETIRED"), ("2027-03-15", "URGENT"), ("2028-09-25", "PLAN"), ("2029-03-31", "TRACK")])
def test_status_thresholds(d, status):
    e = next(e for e in lifecycle.load_register() if e.retires.isoformat() == d)
    assert lifecycle.status(e, TODAY)[0] == status


def test_days_left_arithmetic():
    e = next(e for e in lifecycle.load_register() if e.id == "image-analysis")
    assert lifecycle.status(e, TODAY) == ("PLAN", 674)
    assert lifecycle.status(e, date(2028, 9, 25))[0] == "RETIRED"           # the day it retires counts as retired


def test_exit_code_only_fails_on_retired_by_default(tmp_path):
    write(tmp_path, "a.py", "client.analyze_sentiment(d)\n")
    rows = lifecycle.summarise(lifecycle.scan(tmp_path), TODAY)
    assert lifecycle.exit_code(rows) == 0
    assert lifecycle.exit_code(rows, fail_within_days=900) == 1
    write(tmp_path, "b.py", "from azure.ai.metricsadvisor import MetricsAdvisorClient\n")
    assert lifecycle.exit_code(lifecycle.summarise(lifecycle.scan(tmp_path), TODAY)) == 1


def test_render_mentions_the_plan_by_date_and_source(tmp_path):
    write(tmp_path, "v.py", "import azure.ai.vision.imageanalysis\n")
    text = lifecycle.render(lifecycle.summarise(lifecycle.scan(tmp_path), TODAY), TODAY)
    assert "transition plan by 2026-09-25 (already passed)" in text and "674 days left" in text and "learn.microsoft.com" in text
    assert "v.py:1" in text


def test_render_when_clean():
    assert "No retiring service" in lifecycle.render([], TODAY)


# ---- catalog ---------------------------------------------------------------------------------------------------
def test_catalog_rows_have_host_lifecycle_and_a_learn_page():
    rows = catalog.load()
    assert len(rows) >= 10
    for r in rows:
        assert {"task", "service", "host", "lifecycle", "url"} <= set(r) and r["url"].startswith("https://learn.microsoft.com/")


def test_catalog_lifecycle_matches_the_register():
    reg = {e.service: e.retires.isoformat() for e in lifecycle.load_register()}
    by = {r["service"]: r["lifecycle"] for r in catalog.load()}
    assert by["Vision Image Analysis"] == "retires " + reg["Azure Vision Image Analysis (v3.2 and 4.0)"]
    assert by["Custom Vision"] == "retires " + reg["Azure Custom Vision"]
    assert by["Content Moderator"] == "retires " + reg["Azure Content Moderator"]
    assert by["Language (retiring features)"] == "retires 2029-03-31"


def test_catalog_filter_and_render():
    rows = catalog.find(catalog.load(), "pii")
    assert [r["service"] for r in rows] == ["Language (prebuilt)"]
    assert "Speech" in catalog.render(catalog.find(catalog.load(), "voice"))
    assert catalog.find(catalog.load(), "zzz") == [] and "No service" in catalog.render([])


def test_speech_and_models_are_not_on_the_tools_host():
    by = {r["service"]: r["host"] for r in catalog.load()}
    assert "speech.microsoft.com" in by["Speech"] and by["Foundry models and Agent Service"].endswith("services.ai.azure.com")


# ---- cli -------------------------------------------------------------------------------------------------------
def test_cli_lifecycle_exit_codes(tmp_path, capsys):
    write(tmp_path, "a.py", "client.analyze_sentiment(d)\n")
    assert cli.main(["lifecycle", str(tmp_path), "--today", "2026-11-21", "--no-lines"]) == 0
    assert "TRACK" in capsys.readouterr().out
    assert cli.main(["lifecycle", str(tmp_path), "--today", "2029-04-01"]) == 1
    assert "RETIRED" in capsys.readouterr().out


def test_cli_catalog(capsys):
    assert cli.main(["catalog", "--task", "translate"]) == 0
    assert "Translator" in capsys.readouterr().out


def test_cli_probe_needs_an_endpoint(monkeypatch):
    monkeypatch.delenv("AIPLATFORM_ENDPOINT", raising=False)
    with pytest.raises(SystemExit, match="AIPLATFORM_ENDPOINT"):
        cli.main(["probe"])


def test_cli_refuses_a_regional_endpoint_with_exit_2(monkeypatch, capsys):
    import azure.identity
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", lambda: object())
    assert cli.main(["probe", "--endpoint", "https://westeurope.api.cognitive.microsoft.com"]) == 2
    assert "custom subdomain" in capsys.readouterr().err


def test_cli_missing_path(capsys):
    with pytest.raises(SystemExit, match="No such path"):
        cli.main(["lifecycle", "/nonexistent-path-xyz"])


# ---- bicep -----------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def arm():
    if not shutil.which("bicep"):
        pytest.skip("bicep CLI not installed")
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def res(arm, type_):
    return [r for r in arm["resources"] if r["type"] == type_]


def test_bicep_foundry_resource_is_keyless_multi_service(arm):
    acc = res(arm, "Microsoft.CognitiveServices/accounts")[0]
    assert acc["kind"] == "AIServices" and acc["sku"]["name"] == "S0"
    assert acc["properties"]["disableLocalAuth"] is True and acc["properties"]["customSubDomainName"]
    assert acc["identity"]["type"] == "SystemAssigned"


def test_bicep_diagnostics_go_to_log_analytics_with_the_two_audit_categories(arm):
    d = res(arm, "Microsoft.Insights/diagnosticSettings")[0]["properties"]
    assert {l["category"] for l in d["logs"]} == {"Audit", "RequestResponse"} and d["metrics"][0]["category"] == "AllMetrics"
    assert "workspaces" in d["workspaceId"]
    assert res(arm, "Microsoft.OperationalInsights/workspaces")[0]["properties"]["retentionInDays"] == "[parameters('logRetentionDays')]"


def test_bicep_only_assigns_cognitive_services_user_and_only_when_asked(arm):
    ra = res(arm, "Microsoft.Authorization/roleAssignments")
    assert len(ra) == 1 and arm["variables"]["cognitiveServicesUser"] == "a97b65f3-24c7-4388-baec-2e87135dc908"
    assert "variables('cognitiveServicesUser')" in json.dumps(ra[0])
    assert ra[0]["condition"] == "[not(empty(parameters('developerPrincipalId')))]"
    assert "8e3af657" not in json.dumps(arm)                  # Owner is never granted by the template


def test_bicep_audit_rules_agree_with_the_template(arm):
    """The deployed shape must satisfy our own audit: build an account document from the template and run the rules."""
    from aiplatform import audit
    acc = res(arm, "Microsoft.CognitiveServices/accounts")[0]
    doc = {"name": "n", "kind": acc["kind"], "sku": acc["sku"], "tags": {"owner": "lab", "costcenter": "mglab"},
           "properties": {**acc["properties"], "provisioningState": "Succeeded", "customSubDomainName": "n"}}
    diag = [{"properties": res(arm, "Microsoft.Insights/diagnosticSettings")[0]["properties"]}]
    levels = {f.id: f.level for f in audit.audit(doc, diag, [])}
    assert levels["local-auth"] == "pass" and levels["diagnostics"] == "pass" and levels["kind"] == "pass"
    assert levels["network"] == "warn"                        # known and documented: the demo keeps the public endpoint


def test_bicep_outputs_what_the_cli_needs(arm):
    assert {"endpoint", "resourceId", "accountName"} <= set(arm["outputs"])
