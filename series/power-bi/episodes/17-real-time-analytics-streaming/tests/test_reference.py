import pytest

import events
import reference
from conftest import T0


def test_totals_dedupe_by_event_id(records, plan):
    t = reference.totals(records)
    uniq = events.unique_sales(plan)
    assert t["raw_rows"] == len(plan) and t["events"] == len(uniq) and t["duplicate_rows"] == len(plan) - len(uniq)
    assert t["amount"] == pytest.approx(sum(s.amount for s in uniq), abs=0.01)
    assert t["units"] == sum(s.quantity for s in uniq)
    assert t["amount_raw"] > t["amount"]  # the duplicates inflate a sum over the raw table


def test_dedupe_keeps_the_first_copy():
    rows = [{"EventId": "a", "v": 1}, {"EventId": "b", "v": 2}, {"EventId": "a", "v": 3}]
    assert reference.dedupe(rows) == [{"EventId": "a", "v": 1}, {"EventId": "b", "v": 2}]


def test_the_flash_sale_minutes_are_the_spikes(records):
    online = reference.per_minute(records, "Online")
    assert set(reference.spike_minutes(online)) == {"2026-11-24T10:06:00Z", "2026-11-24T10:07:00Z"}


def test_a_flat_series_has_no_spike():
    assert reference.spike_minutes({f"m{i}": 10.0 for i in range(10)}) == []
    assert reference.spike_minutes({"a": 1.0, "b": 2.0}) == []  # fewer than four minutes: no verdict


def test_spike_with_zero_mad():
    s = {f"m{i}": 5.0 for i in range(9)}
    s["m9"] = 50.0
    assert reference.spike_minutes(s) == ["m9"]


def test_per_minute_orders_and_amount(records):
    orders = reference.per_minute(records)
    amount = reference.per_minute(records, measure="amount")
    assert sum(orders.values()) == reference.totals(records)["events"]
    assert sum(amount.values()) == pytest.approx(reference.totals(records)["amount"], abs=0.05)
    assert list(orders) == sorted(orders)
    with pytest.raises(ValueError):
        reference.per_minute(records, measure="x")


def test_minute_bucket_is_bin_1m(records):
    r = {"EventTime": "2026-11-24T10:06:59.999Z"}
    assert reference.minute_of(r) == "2026-11-24T10:06:00Z"
