"""Telemetry model: what a Contoso cold-room sensor sends, and what a message costs on the free tier.

Pure functions, no network. The simulator and the tests both use them.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Learn (IoT Hub quotas): F1 allows 8,000 messages/day and meters messages in 0.5 KB blocks.
FREE_TIER_MESSAGES_PER_DAY = 8000
FREE_TIER_METER_BYTES = 512
# Same threshold the Stream Analytics query alerts on (asa/coldroom-telemetry.asaql).
ALERT_TEMP_C = 8.0

SCENARIOS = ("normal", "door-open", "dirty")


@dataclass(frozen=True)
class ColdRoom:
    device_id: str
    setpoint_c: float = 4.0


DEFAULT_ROOMS = (
    ColdRoom("coldroom-01", 4.0),
    ColdRoom("coldroom-02", 3.5),
    ColdRoom("coldroom-03", 5.0),
)


def iso_utc(moment: datetime) -> str:
    """ISO 8601 in UTC with a trailing Z, the form TIMESTAMP BY reads without ambiguity."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def make_reading(room: ColdRoom, moment: datetime, tick: int, scenario: str, rng: random.Random) -> dict:
    """One telemetry payload. `tick` counts messages already sent by this device.

    normal     setpoint with small noise
    door-open  from tick 13 coldroom-02 sits 6 C warmer (a door left open), to show the alert
    dirty      like normal, but every 7th message is malformed (string, null, missing field)
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; use one of {', '.join(SCENARIOS)}")
    temperature = room.setpoint_c + rng.uniform(-0.4, 0.4)
    if scenario == "door-open" and room.device_id == DEFAULT_ROOMS[1].device_id and tick > 12:
        temperature += 6.0
    payload = {
        "deviceId": room.device_id,
        "temperatureC": round(temperature, 2),
        "humidityPct": round(55 + rng.uniform(-5, 5), 1),
        "observedAt": iso_utc(moment),
    }
    if scenario == "dirty" and tick % 7 == 6:
        kind = (tick // 7) % 3
        if kind == 0:
            payload["temperatureC"] = "n/a"
        elif kind == 1:
            payload["temperatureC"] = None
        else:
            del payload["temperatureC"]
    return payload


def encode(payload: dict) -> tuple[bytes, str, str]:
    """Body plus the two properties IoT Hub routing needs to read a JSON body."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return body, "application/json", "utf-8"


def metered_messages(body_size: int, meter_bytes: int = FREE_TIER_METER_BYTES) -> int:
    """A message larger than the meter size counts as several messages."""
    return max(1, math.ceil(body_size / meter_bytes))


def estimate_daily_cost(devices: int, interval_seconds: float, duration_seconds: float, body_size: int = 150) -> int:
    """Messages counted against the daily quota by one run."""
    if devices < 1 or interval_seconds <= 0 or duration_seconds <= 0:
        raise ValueError("devices, interval and duration must be positive")
    per_device = math.floor(duration_seconds / interval_seconds) + 1
    return devices * per_device * metered_messages(body_size)


class QuotaExceeded(Exception):
    pass


def check_budget(devices: int, interval_seconds: float, duration_seconds: float, *, already_sent_today: int = 0,
                 headroom: float = 0.8, body_size: int = 150) -> int:
    """Refuse a run that would use more than `headroom` of the free-tier daily quota."""
    cost = estimate_daily_cost(devices, interval_seconds, duration_seconds, body_size)
    limit = int(FREE_TIER_MESSAGES_PER_DAY * headroom)
    if already_sent_today + cost > limit:
        raise QuotaExceeded(
            f"run needs {cost} messages, {already_sent_today} already sent today, "
            f"limit with headroom is {limit} of {FREE_TIER_MESSAGES_PER_DAY}"
        )
    return cost


def schedule(start: datetime, interval_seconds: float, count: int) -> list[datetime]:
    return [start + timedelta(seconds=interval_seconds * i) for i in range(count)]
