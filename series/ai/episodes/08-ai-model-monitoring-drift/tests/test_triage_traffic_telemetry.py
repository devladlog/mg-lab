import json
import logging

import pytest

from hrmon import telemetry, traffic
from hrmon.triage import triage


def test_triage_uses_strict_schema_entra_token_and_records_the_served_model(client, aoai_stub):
    t = triage(client, "chat", "My payslip is missing the overtime from last month.")
    assert (t.category, t.needs_human, t.model) == ("payroll", True, "gpt-5-mini-2025-08-07")
    assert t.prompt_tokens == 120 and t.completion_tokens == 30 and t.latency_ms >= 0
    req = aoai_stub.requests[-1]
    assert req["path"] == "/openai/v1/chat/completions" and req["auth"] == "Bearer fake-entra-token"
    body = req["body"]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in body and body["max_completion_tokens"] == 2000
    assert client.test_credential.scopes == ["https://ai.azure.com/.default"]


def test_window_records_contain_features_and_answers_but_never_the_question(client, aoai_stub):
    records = []
    qs = traffic.load(traffic.Path(__file__).resolve().parents[1] / "data" / "current.jsonl")
    failures = traffic.run_window(client, "chat", "current", qs, lambda m, a: records.append({"message": m, **a}))
    assert failures == 0 and len(records) == 40
    r = records[0]
    assert r["message"] == "triage" and r["hr_window"] == "current"
    assert set(r) >= {"hr_lang", "hr_length", "hr_category", "hr_urgency", "hr_needs_human", "hr_model",
                      "hr_latency_ms", "hr_prompt_tokens", "hr_completion_tokens"}
    blob = json.dumps(records, ensure_ascii=False)
    assert not any(q["question"] in blob for q in qs)          # privacy: no question text in telemetry


def test_a_failed_call_is_recorded_and_the_window_continues(client, aoai_stub):
    aoai_stub.fail_on = "parental leave"
    records = []
    qs = [{"question": "How do I request parental leave?"}, {"question": "When are bonuses paid this year?"}]
    failures = traffic.run_window(client, "chat", "w1", qs, lambda m, a: records.append({"message": m, **a}))
    assert failures == 1 and [r["message"] for r in records] == ["triage_error", "triage"]
    assert records[0]["hr_error"] == "InternalServerError"


def test_golden_accuracy_drops_when_the_model_behaves_differently(client, aoai_stub):
    golden = traffic.load(traffic.Path(__file__).resolve().parents[1] / "data" / "golden.jsonl")
    sink = []
    good = traffic.run_golden(client, "chat", "baseline", golden, lambda m, a: sink.append(a))
    aoai_stub.override = {"hybrid": "other", "híbrido": "other"}      # e.g. a new model version
    worse = traffic.run_golden(client, "chat", "current", golden, lambda m, a: sink.append(a))
    assert good == 1.0 and worse == pytest.approx(12 / 16)
    assert sink[-1] == {"hr_window": "current", "hr_golden_accuracy": 0.75, "hr_golden_n": 16}


def test_attributes_are_validated():
    with pytest.raises(ValueError):
        telemetry.attributes('x" or 1==1 //')          # also protects the KQL string built from it
    with pytest.raises(TypeError):
        telemetry.attributes("w", bad=["list"])


def test_log_records_reach_opentelemetry_with_attributes():
    """Same path the distro uses: Python logging -> OpenTelemetry LoggingHandler -> log record exporter."""
    from opentelemetry.instrumentation.logging.handler import LoggingHandler
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor

    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    log = logging.getLogger(telemetry.LOGGER_NAME)
    log.addHandler(handler)
    try:
        telemetry.emit("triage", telemetry.attributes("baseline", category="leave", needs_human=False, latency_ms=812))
    finally:
        log.removeHandler(handler)
    (rec,) = exporter.get_finished_logs()
    lr = getattr(rec, "log_record", rec)
    assert lr.body == "triage"
    attrs = dict(lr.attributes)
    assert attrs["hr_window"] == "baseline" and attrs["hr_category"] == "leave" and attrs["hr_latency_ms"] == 812


def test_traffic_cli_writes_local_records(aoai_stub, tmp_path, monkeypatch, capsys):
    from conftest import FakeCredential
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", FakeCredential)
    out = tmp_path / "records.jsonl"
    data = traffic.Path(__file__).resolve().parents[1] / "data"
    code = traffic.main(["--data", str(data / "baseline.jsonl"), "--window", "baseline", "--aoai-endpoint",
                         aoai_stub.url, "--golden", str(data / "golden.jsonl"), "--local-out", str(out),
                         "--pause", "0"])
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert code == 0 and len(lines) == 41 and lines[-1]["message"] == "quality"
    assert "window baseline: 40 triaged, 0 failed" in capsys.readouterr().out


def test_azure_monitor_setup_is_keyless_and_scoped_to_our_logger(monkeypatch):
    import microsoft.opentelemetry as mot
    seen = {}
    monkeypatch.setattr(mot, "use_microsoft_opentelemetry", lambda **kw: seen.update(kw))
    cred = object()
    telemetry.setup_azure_monitor("InstrumentationKey=00000000-0000-0000-0000-000000000000", cred)
    assert seen["enable_azure_monitor"] is True and seen["azure_monitor_exporter_credential"] is cred
    assert seen["logger_name"] == "hrmon" and seen["enable_sensitive_data"] is False
