import json
from datetime import timedelta

import pytest

from conftest import FakeCredential, FakeLogAnalytics, logs_client
from hrmon import logs, monitor, traffic

DATA = traffic.Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def records(client, aoai_stub):
    """Both windows through the stub model (keyword rules), plus golden runs; current uses a 'new model version'."""
    out = []
    sink = lambda m, a: out.append({"message": m, **a})
    golden = traffic.load(DATA / "golden.jsonl")
    traffic.run_window(client, "chat", "baseline", traffic.load(DATA / "baseline.jsonl"), sink)
    traffic.run_golden(client, "chat", "baseline", golden, sink)
    aoai_stub.model = "gpt-5-mini-2025-08-07"
    traffic.run_window(client, "chat", "current", traffic.load(DATA / "current.jsonl"), sink)
    traffic.run_golden(client, "chat", "current", golden, sink)
    return out


def test_kql_reads_apptraces_properties_for_both_windows():
    q = logs.records_query(["baseline", "current"])
    assert q.startswith("AppTraces") and 'where window in ("baseline", "current")' in q
    assert 'category = tostring(Properties["hr_category"])' in q and "take 10000" in q
    with pytest.raises(ValueError):
        logs.records_query(['current") | union SecurityEvent //'])


def test_fetch_uses_the_real_logs_client(records):
    adapter = FakeLogAnalytics(records)
    client = logs_client(adapter)
    rows = logs.fetch(client, "00000000-0000-0000-0000-000000000000", ["baseline", "current"], timedelta(hours=6))
    (req,) = adapter.requests
    assert req["url"] == "https://api.loganalytics.io/v1/workspaces/00000000-0000-0000-0000-000000000000/query"
    assert req["body"]["timespan"] == "PT21600.0S" and req["headers"]["Authorization"] == "Bearer fake-entra-token"
    assert client.test_credential.scopes == ["https://api.loganalytics.io/.default"]
    assert len([r for r in rows if r["message"] == "triage"]) == 80
    assert {r["hr_window"] for r in rows} == {"baseline", "current"}


def test_partial_results_are_an_error_not_silent_data_loss(records):
    adapter = FakeLogAnalytics(records)
    adapter.partial = True
    with pytest.raises(RuntimeError, match="partial result"):
        logs.fetch(logs_client(adapter), "ws", ["baseline", "current"])


def test_analysis_finds_language_and_category_drift(records):
    rep = monitor.analyse(records, "baseline", "current")
    by = {f.feature: f for f in rep.features}
    assert by["lang"].drifted and by["category"].drifted        # Portuguese up; hybrid allowance -> benefits
    assert not rep.model_changed and rep.quality == {"baseline": 1.0, "current": 1.0}
    assert rep.alert and rep.max_psi >= 0.2
    text = monitor.render(rep, "baseline", "current")
    assert "ALERT: YES" in text and "lang" in text and "pt " in text


def test_same_population_does_not_alert(client, aoai_stub):
    out = []
    qs = traffic.load(DATA / "baseline.jsonl")
    traffic.run_window(client, "chat", "w1", qs, lambda m, a: out.append({"message": m, **a}))
    traffic.run_window(client, "chat", "w2", qs, lambda m, a: out.append({"message": m, **a}))
    rep = monitor.analyse(out, "w1", "w2")
    assert not rep.alert and rep.max_psi == pytest.approx(0, abs=1e-9)


def test_model_version_change_and_quality_drop_alert_on_their_own(client, aoai_stub):
    out = []
    sink = lambda m, a: out.append({"message": m, **a})
    qs, golden = traffic.load(DATA / "baseline.jsonl"), traffic.load(DATA / "golden.jsonl")
    traffic.run_window(client, "chat", "w1", qs, sink)
    traffic.run_golden(client, "chat", "w1", golden, sink)
    aoai_stub.model = "gpt-5-mini-2026-01-15"                     # someone let the deployment auto-upgrade
    aoai_stub.override = {"hybrid": "other", "híbrido": "other"}
    traffic.run_window(client, "chat", "w2", qs, sink)
    traffic.run_golden(client, "chat", "w2", golden, sink)
    rep = monitor.analyse(out, "w1", "w2")
    assert not any(f.drifted for f in rep.features)              # inputs and outputs look the same...
    assert rep.model_changed and rep.quality_dropped and rep.alert   # ...but the model and the quality changed


def test_monitor_cli_local_exit_codes(records, tmp_path, capsys):
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    assert monitor.main(["--local", str(path), "--baseline", "baseline", "--current", "current"]) == 1
    assert "ALERT: YES" in capsys.readouterr().out
    assert monitor.main(["--local", str(path), "--baseline", "baseline", "--current", "baseline"]) == 0


def test_monitor_cli_against_log_analytics(records, monkeypatch, capsys):
    adapter = FakeLogAnalytics(records)
    import azure.monitor.query as amq
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", FakeCredential)
    monkeypatch.setattr(amq, "LogsQueryClient", lambda cred: logs_client(adapter))
    code = monitor.main(["--workspace-id", "ws", "--baseline", "baseline", "--current", "current",
                         "--lookback-hours", "2"])
    assert code == 1 and adapter.requests[0]["body"]["timespan"] == "PT7200.0S"
