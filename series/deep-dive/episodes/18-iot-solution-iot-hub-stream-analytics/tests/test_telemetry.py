import json
import random
from datetime import datetime, timezone

import pytest

from iotlab.telemetry import (ALERT_TEMP_C, DEFAULT_ROOMS, FREE_TIER_MESSAGES_PER_DAY, QuotaExceeded, check_budget,
                              encode, estimate_daily_cost, iso_utc, make_reading, metered_messages)

T0 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)


def readings(scenario, ticks=30):
    rng = random.Random(1)
    return [make_reading(room, T0, tick, scenario, rng) for tick in range(ticks) for room in DEFAULT_ROOMS]


def test_payload_has_the_fields_the_query_reads():
    sample = readings("normal", 1)[0]
    assert set(sample) == {"deviceId", "temperatureC", "humidityPct", "observedAt"}
    assert sample["observedAt"] == "2026-11-20T10:00:00.000Z"


def test_normal_stays_far_below_the_alert_threshold():
    assert max(r["temperatureC"] for r in readings("normal")) < ALERT_TEMP_C - 2


def test_door_open_only_warms_coldroom_02_after_tick_12():
    rng = random.Random(1)
    room = DEFAULT_ROOMS[1]
    before = make_reading(room, T0, 12, "door-open", rng)["temperatureC"]
    after = make_reading(room, T0, 13, "door-open", rng)["temperatureC"]
    assert before < 5 and after > ALERT_TEMP_C
    other = make_reading(DEFAULT_ROOMS[0], T0, 20, "door-open", rng)["temperatureC"]
    assert other < 5


def test_dirty_scenario_injects_each_kind_of_bad_message():
    rows = [r for r in readings("dirty", 60)]
    assert any(r.get("temperatureC") == "n/a" for r in rows)
    assert any("temperatureC" in r and r["temperatureC"] is None for r in rows)
    assert any("temperatureC" not in r for r in rows)
    assert sum(1 for r in rows if isinstance(r.get("temperatureC"), float)) > len(rows) * 0.8


def test_unknown_scenario_is_refused():
    with pytest.raises(ValueError, match="unknown scenario"):
        make_reading(DEFAULT_ROOMS[0], T0, 0, "meltdown", random.Random(1))


def test_encode_is_compact_utf8_json_with_content_type():
    body, ctype, enc = encode({"deviceId": "coldroom-01", "temperatureC": 4.0})
    assert json.loads(body)["deviceId"] == "coldroom-01"
    assert b" " not in body and (ctype, enc) == ("application/json", "utf-8")


def test_a_message_is_far_below_the_free_tier_meter_size():
    body, _, _ = encode(make_reading(DEFAULT_ROOMS[0], T0, 0, "normal", random.Random(1)))
    assert len(body) < 200 and metered_messages(len(body)) == 1


def test_large_message_counts_as_several_on_the_free_tier():
    assert metered_messages(512) == 1 and metered_messages(513) == 2 and metered_messages(4096) == 8


def test_default_demo_run_is_a_small_part_of_the_daily_quota():
    # 3 devices, every 5 s, 20 minutes: 3 x 241 messages
    assert estimate_daily_cost(3, 5, 20 * 60) == 723
    assert 723 < FREE_TIER_MESSAGES_PER_DAY * 0.1


def test_budget_guard_refuses_a_run_that_would_exhaust_the_day():
    with pytest.raises(QuotaExceeded, match="limit with headroom is 6400"):
        check_budget(3, 5, 3 * 3600)  # three hours at 5 s: 6,495 messages... plus the headroom rule
    with pytest.raises(QuotaExceeded):
        check_budget(3, 5, 20 * 60, already_sent_today=6000)
    assert check_budget(3, 5, 20 * 60, already_sent_today=1000) == 723


def test_iso_utc_has_milliseconds_and_z():
    assert iso_utc(datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=timezone.utc)) == "2026-01-02T03:04:05.678Z"
