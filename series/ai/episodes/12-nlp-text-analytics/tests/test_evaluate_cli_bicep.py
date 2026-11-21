import json
import shutil
import subprocess

import pytest

from conftest import ROOT, FakeCredential, FakeService, FakeTransport
from ticketnlp import cli, evaluate as ev
from ticketnlp.analyzer import Analyzer
from ticketnlp.client import make_client


def factory(service):
    t = FakeTransport(service)
    c = make_client("https://contoso-lang.cognitiveservices.azure.com", FakeCredential(), transport=t, retry_total=0)
    return lambda: Analyzer(c)


def test_the_case_file_is_well_formed_fictional_and_covers_the_hard_situations():
    cases = ev.load_cases()
    ids = {c["id"] for c in cases}
    assert len(cases) == 13 and {"long-thread", "blank", "en-emoji", "mixed-language", "en-badge-id"} <= ids
    assert {c["language"] for c in cases if c["language"]} == {"en", "pt", "es"}
    assert next(c for c in cases if c["id"] == "long-thread")["text"].__len__() > 5120
    text = json.dumps(cases)
    assert "@contoso.com" in text and all(x not in text for x in ("devladlog", "gmail", "outlook.com"))     # fictional addresses only


def test_with_redaction_first_the_gate_passes_and_nothing_leaks(service):
    s, results = ev.score(factory(service), ev.load_cases())
    assert s.leaks == [] and s.problems == [] and s.mismatches == [] and ev.gate(s)[0]
    assert s.language_n == 11 and s.sentiment_n == 10 and s.language_acc == 1.0
    assert s.requests["pii"] == 3 and s.requests["language"] == 1                    # 13 chunks of PII, 5 per request


def test_analysing_the_raw_text_leaks_through_phrases_and_entities(service):
    s, _ = ev.score(factory(service), ev.load_cases(), redact=False)
    assert any("Alex Demo" in x for x in s.leaks) and not ev.gate(s)[0]


def test_a_pii_miss_by_the_service_is_caught_by_the_gate(service):
    class BlindToPhones(FakeService):
        def _PiiEntityRecognition(self, d, p):
            r = super()._PiiEntityRecognition(d, p)
            return {**r, "redactedText": d["text"]} if "911" in d["text"] or "912" in d["text"] else r
    s, _ = ev.score(factory(BlindToPhones()), ev.load_cases())
    ok, why = ev.gate(s)
    assert not ok and "+351 912 345 678" in why[0] and "survived" in why[0]


def test_leak_matching_ignores_case_spacing_and_phone_formatting():
    from ticketnlp.pipeline import Analysis
    a = Analysis("x", redacted_text="call  +351-912-345-678 today", key_phrases=["ALEX   demo"])
    assert ev.leaked(a, ["+351 912 345 678", "Alex Demo", "nothing here"]) == ["+351 912 345 678", "Alex Demo"]


def test_accuracy_gates_fail_on_wrong_language_or_sentiment(service):
    service.language_override = {"en-neg-vpn": ("fr", .99), "en-pos-thanks": ("fr", .99), "en-neutral-install": ("fr", .99)}
    s, _ = ev.score(factory(service), ev.load_cases())
    ok, why = ev.gate(s)
    assert not ok and any("language accuracy" in w for w in why) and any("expected 'en'" in m for m in s.mismatches)


def test_a_failing_document_is_reported_and_gated(service):
    service.fail_pii_for = {"en-neutral-install#0"}
    s, _ = ev.score(factory(service), ev.load_cases())
    ok, why = ev.gate(s)
    assert not ok and any("en-neutral-install" in p for p in s.problems)


def test_the_report_names_both_modes_and_the_result_line(service):
    f = factory(service)
    text = ev.format_report([ev.score(f, ev.load_cases())[0], ev.score(f, ev.load_cases(), redact=False)[0]])
    assert "redact first" in text and "analyse raw text" in text and "RESULT (redact first): PASS" in text and "LEAK" in text


def run_cli(monkeypatch, service, *argv):
    t = FakeTransport(service)
    monkeypatch.setattr(cli, "make_client", lambda endpoint: make_client(endpoint, FakeCredential(), transport=t, retry_total=0))
    return cli.main(list(argv))


def test_cli_limits_needs_no_endpoint(capsys):
    assert cli.main(["limits"]) == 0
    out = capsys.readouterr().out
    assert "characters per document: 5120" in out and "free tier: 5000 text records a month" in out and "13 tickets -> 13 chunks" in out


def test_cli_analyze_writes_a_report_without_ticket_text_and_a_redacted_json(monkeypatch, service, tmp_path, capsys):
    rc = run_cli(monkeypatch, service, "analyze", "--endpoint", "https://x.cognitiveservices.azure.com",
                 "--out", str(tmp_path / "r.md"), "--json", str(tmp_path / "a.json"))
    md, js = (tmp_path / "r.md").read_text(encoding="utf-8"), (tmp_path / "a.json").read_text(encoding="utf-8")
    assert rc == 0 and "# Ticket analysis: 13 tickets" in md and "priority-review" in md
    for secret in ("alex.demo@contoso.com", "912 345 678", "CON-48213", "Taylor Demo"):
        assert secret not in md and secret not in js


def test_cli_show_prints_original_next_to_redacted_and_the_route(monkeypatch, service, capsys):
    assert run_cli(monkeypatch, service, "show", "--endpoint", "https://x", "--id", "en-neg-vpn") == 0
    out = capsys.readouterr().out
    orig, red = [l for l in out.splitlines() if l.startswith(("original", "redacted"))]
    assert "Alex Demo" in orig and "Alex Demo" not in red and "alex.demo@contoso.com" not in red
    assert "next step  : ('priority-review'" in out and "('VPN', 'negative')" in out
    with pytest.raises(SystemExit) as e:
        run_cli(monkeypatch, service, "show", "--endpoint", "https://x", "--id", "nope")
    assert "no ticket with id 'nope'" in str(e.value)


def test_cli_evaluate_exit_codes_follow_the_gate(monkeypatch, service, capsys):
    assert run_cli(monkeypatch, service, "evaluate", "--endpoint", "https://x", "--compare") == 0
    assert "LEAK" in capsys.readouterr().out
    service.fail_pii_for = {"en-neutral-install#0"}
    assert run_cli(monkeypatch, service, "evaluate", "--endpoint", "https://x") == 1


def test_cli_without_endpoint_and_with_a_failing_service(monkeypatch, service, capsys):
    monkeypatch.delenv("TICKETNLP_ENDPOINT", raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["evaluate"])
    assert "TICKETNLP_ENDPOINT" in str(e.value)
    service.status_override = 500
    assert run_cli(monkeypatch, service, "analyze", "--endpoint", "https://x", "--out", "/tmp/ticketnlp-unused.md") == 2
    assert "error:" in capsys.readouterr().err


needs_bicep = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--outfile", str(out)], check=True, capture_output=True)
    return json.loads(out.read_text())


@needs_bicep
def test_bicep_is_a_keyless_language_resource_with_a_free_tier_default_and_reader_role_only(template):
    arm = template["resources"]
    acct = next(r for r in arm if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acct["kind"] == "TextAnalytics" and acct["properties"]["disableLocalAuth"] is True
    assert acct["properties"]["customSubDomainName"] and acct["sku"]["name"] == "[parameters('skuName')]"
    assert template["parameters"]["skuName"]["defaultValue"] == "F0" and template["parameters"]["skuName"]["allowedValues"] == ["F0", "S"]
    roles = [r for r in arm if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(roles) == 1 and template["variables"]["languageReader"] == "7628b7b8-a8b2-4cdc-b46f-e9b35248918e"
    assert "a97b65f3" not in json.dumps(template)                    # not Cognitive Services User (listkeys, all data actions)
