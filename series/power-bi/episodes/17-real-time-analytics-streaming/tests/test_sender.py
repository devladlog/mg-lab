import json
from datetime import timedelta

import pytest

import events
import reference
import sender
from conftest import T0


class ListTransport:
    def __init__(self):
        self.calls = []

    def send(self, payloads):
        self.calls.append(list(payloads))
        return 1 if payloads else 0

    def close(self):
        pass


def test_summary_counts_match_the_plan(plan):
    t = ListTransport()
    s = sender.run(plan, t, t0=T0, realtime=False)
    uniq = events.unique_sales(plan)
    assert s.messages == len(plan) == sum(len(c) for c in t.calls)
    assert s.unique_events == len(uniq)
    assert s.duplicates == len(plan) - len(uniq)
    assert s.late == sum(1 for e in plan if e.kind == "late")
    assert s.amount == pytest.approx(sum(x.amount for x in uniq), abs=0.01)
    assert sum(s.by_store.values()) == s.unique_events


def test_summary_agrees_with_the_reference_on_what_was_sent(plan):
    """The sender's summary and the reference read from the payload must give the same totals: this is the 'totals check'."""
    t = ListTransport()
    s = sender.run(plan, t, t0=T0, realtime=False)
    sent = [json.loads(p) for c in t.calls for p in c]
    ref = reference.totals(sent)
    assert ref["events"] == s.unique_events and ref["duplicate_rows"] == s.duplicates
    assert ref["amount"] == pytest.approx(s.amount, abs=0.01)


def test_pacing_waits_for_each_batch_and_never_sends_early(plan):
    now = [0.0]
    sleeps = []

    def sleep(x):
        sleeps.append(x)
        now[0] += x

    t = ListTransport()
    sender.run(plan[:40], t, t0=T0, clock=lambda: now[0], sleep=sleep, window_s=2.0)
    assert sleeps and all(x > 0 for x in sleeps)
    assert now[0] == pytest.approx(plan[:40][-1].send_at, abs=2.0)
    assert len(t.calls) > 1


def test_start_delay_is_waited_before_the_first_message(plan):
    now = [0.0]
    waited = []
    t = ListTransport()
    sender.run(plan[:3], t, t0=T0, clock=lambda: now[0], sleep=lambda x: (waited.append(x), now.__setitem__(0, now[0] + x)), start_delay=30.0)
    assert waited[0] >= 30.0 - 1e-9


def test_speed_plays_the_run_faster(plan):
    now = [0.0]

    def sleep(x):
        now[0] += x

    sender.run(plan, ListTransport(), t0=T0, clock=lambda: now[0], sleep=sleep, speed=10.0)
    assert now[0] < (plan[-1].send_at / 10) + 2


def test_event_times_follow_t0_and_speed(plan):
    t = ListTransport()
    sender.run(plan[:5], t, t0=T0, realtime=False, speed=2.0)
    first = json.loads(t.calls[0][0])
    assert first["EventTime"].startswith("2026-11-24T10:00:")


@pytest.mark.parametrize("kw", [{"speed": 0}, {"window_s": 0}])
def test_bad_pacing_arguments(plan, kw):
    with pytest.raises(ValueError):
        sender.run(plan, ListTransport(), **kw)


def test_next_minute():
    from datetime import datetime, timezone
    assert sender.next_minute(datetime(2026, 11, 24, 10, 0, 0, 5, tzinfo=timezone.utc)) == T0 + timedelta(minutes=1)
    assert sender.next_minute(datetime(2026, 11, 24, 10, 59, 59, tzinfo=timezone.utc)) == T0 + timedelta(hours=1)


def test_ndjson_transport_round_trip(plan, tmp_path):
    f = tmp_path / "run.ndjson"
    tr = sender.NdjsonTransport(f)
    s = sender.run(plan, tr, t0=T0, realtime=False)
    tr.close()
    rows = reference.read_ndjson(f)
    assert len(rows) == s.messages
    assert reference.totals(rows)["events"] == s.unique_events


class FakeBatch:
    def __init__(self, limit):
        self.items, self.limit = [], limit

    def add(self, e):
        if len(self.items) >= self.limit:
            raise ValueError("The EventDataBatch has reached its size limit")  # what azure-eventhub raises
        self.items.append(e)

    def __len__(self):
        return len(self.items)


class FakeProducer:
    def __init__(self, limit):
        self.limit, self.sent, self.closed = limit, [], False

    def create_batch(self):
        return FakeBatch(self.limit)

    def send_batch(self, b):
        self.sent.append(b)

    def close(self):
        self.closed = True


def test_event_hub_transport_splits_a_full_batch_and_sends_every_payload():
    pytest.importorskip("azure.eventhub")
    p = FakeProducer(limit=4)
    tr = sender.EventHubTransport("unused", producer=p)
    n = tr.send([f'{{"i":{i}}}' for i in range(10)])
    assert n == 3 == len(p.sent)
    bodies = [e.body_as_str() for b in p.sent for e in b.items]
    assert bodies == [f'{{"i":{i}}}' for i in range(10)]
    tr.send([])  # nothing to send: no empty batch goes out
    assert len(p.sent) == 3
    tr.close()
    assert p.closed


def test_event_hub_transport_builds_the_real_client_from_a_connection_string_without_connecting():
    pytest.importorskip("azure.eventhub")
    conn = "Endpoint=sb://eventstream-00000000.servicebus.windows.net/;SharedAccessKeyName=key_0;SharedAccessKey=AAAA;EntityPath=es_0"
    tr = sender.EventHubTransport(conn)
    assert tr._producer.eventhub_name == "es_0"
    tr.close()
