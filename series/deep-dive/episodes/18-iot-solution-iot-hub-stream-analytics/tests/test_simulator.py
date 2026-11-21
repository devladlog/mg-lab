import json
from datetime import datetime, timedelta, timezone

import pytest

from iotlab.__main__ import main
from iotlab.simulator import run
from iotlab.telemetry import DEFAULT_ROOMS, QuotaExceeded

CONNECTION = {r.device_id: f"HostName=iot-contoso-demo.azure-devices.net;DeviceId={r.device_id};SharedAccessKey=AAAA" for r in DEFAULT_ROOMS}


class FakeClient:
    def __init__(self, connection_string, fail_every=0):
        self.connection_string = connection_string
        self.sent = []
        self.closed = False
        self.fail_every = fail_every

    def send(self, body, content_type, content_encoding):
        if self.fail_every and (len(self.sent) + 1) % self.fail_every == 0:
            self.sent.append(None)
            raise ConnectionError("link dropped")
        self.sent.append((json.loads(body), content_type, content_encoding))

    def close(self):
        self.closed = True


def make_run(**kwargs):
    fail_every = kwargs.pop("fail_every", 0)
    clients = {}
    now = [datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)]
    sleeps = []

    def factory(connection_string):
        client = FakeClient(connection_string, fail_every)
        clients[connection_string] = client
        return client

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += timedelta(seconds=seconds)

    stats = run(DEFAULT_ROOMS, CONNECTION, client_factory=factory, clock=lambda: now[0], sleep=sleep, **kwargs)
    return stats, clients, sleeps


def test_every_device_sends_every_tick_and_clients_are_closed():
    stats, clients, sleeps = make_run(interval_seconds=5, duration_seconds=60)
    assert stats.sent == 3 * 13 and stats.failed == 0
    assert all(c.closed for c in clients.values())
    assert sleeps == [5] * 12  # no sleep after the last tick


def test_messages_carry_content_type_and_device_ids_and_increasing_event_time():
    _, clients, _ = make_run(interval_seconds=5, duration_seconds=20)
    first = clients[CONNECTION["coldroom-01"]].sent
    assert {m[1:] for m in first} == {("application/json", "utf-8")}
    assert [m[0]["deviceId"] for m in first] == ["coldroom-01"] * 5
    times = [m[0]["observedAt"] for m in first]
    assert times == sorted(times) and len(set(times)) == 5


def test_a_failing_link_is_counted_and_the_fleet_keeps_running():
    stats, _, _ = make_run(interval_seconds=5, duration_seconds=30, fail_every=4)
    assert stats.failed > 0 and stats.sent + stats.failed == 3 * 7


def test_missing_connection_string_is_reported_before_anything_is_sent():
    with pytest.raises(KeyError, match="coldroom-03"):
        run(DEFAULT_ROOMS, {"coldroom-01": "x", "coldroom-02": "y"}, client_factory=lambda s: FakeClient(s))


def test_quota_guard_runs_before_any_client_is_created():
    created = []
    with pytest.raises(QuotaExceeded):
        run(DEFAULT_ROOMS, CONNECTION, interval_seconds=1, duration_seconds=4 * 3600,
            client_factory=lambda s: created.append(s))
    assert created == []


def test_cli_sample_prints_json_lines(capsys):
    assert main(["sample", "--scenario", "door-open", "--count", "2"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 6 and all(json.loads(line)["deviceId"].startswith("coldroom-") for line in lines)


def test_cli_budget_matches_the_estimate(capsys):
    assert main(["budget", "--devices", "3", "--interval", "5", "--minutes", "20"]) == 0
    assert capsys.readouterr().out.startswith("723 messages of the 8000")


def test_cli_simulate_refuses_instead_of_burning_the_quota(tmp_path, capsys):
    cfg = tmp_path / "devices.local.json"
    cfg.write_text(json.dumps(CONNECTION))
    assert main(["simulate", "--file", str(cfg), "--interval", "1", "--minutes", "240"]) == 2
    assert "refused" in capsys.readouterr().err


def test_real_sdk_is_importable_and_has_the_calls_the_client_uses():
    sdk = pytest.importorskip("azure.iot.device")
    for name in ("create_from_connection_string", "connect", "send_message", "shutdown"):
        assert hasattr(sdk.IoTHubDeviceClient, name)
    message = sdk.Message(b"{}")
    message.content_type = "application/json"
    message.content_encoding = "utf-8"
    assert message.content_type == "application/json"
