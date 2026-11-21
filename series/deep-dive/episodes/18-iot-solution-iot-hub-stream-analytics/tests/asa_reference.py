"""An independent, small model of what asa/coldroom-telemetry.asaql should produce.

It exists to write the expected outputs of the query test cases without copying the answer from the engine:
the real Stream Analytics local runtime (azure-streamanalytics-cicd) then has to agree with it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

ALERT_AVG_C = 8.0
ALERT_MIN_READINGS = 3


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


def _temperature(value):
    """TRY_CAST(x AS float): numbers and numeric strings count, anything else is NULL."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def valid_readings(events: list[dict]) -> list[tuple[str, datetime, float]]:
    out = []
    for event in events:
        device = event.get("deviceId")
        temp = _temperature(event.get("temperatureC"))
        if device is None or temp is None:
            continue
        out.append((device, _parse(event["observedAt"]), temp))
    return out


def _window_end_for(moment: datetime, hop: timedelta) -> datetime:
    """A window (end - size, end] holds events with end - size < t <= end. First end at or after t."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    steps = -((epoch - moment) // hop)  # ceil((t - epoch) / hop)
    return epoch + steps * hop


def _windows(events, size: timedelta, hop: timedelta):
    buckets = defaultdict(list)
    for device, moment, temp in events:
        end = _window_end_for(moment, hop)
        while end - size < moment:
            buckets[(device, end)].append(temp)
            end += hop
    return buckets


def expected_aggregates(events: list[dict]) -> list[dict]:
    rows = []
    for (device, end), temps in _windows(valid_readings(events), timedelta(minutes=1), timedelta(minutes=1)).items():
        rows.append({
            "deviceId": device, "windowEnd": _fmt(end), "readings": len(temps),
            "avgTempC": sum(temps) / len(temps), "minTempC": min(temps), "maxTempC": max(temps),
        })
    return sorted(rows, key=lambda r: (r["windowEnd"], r["deviceId"]))


def expected_alerts(events: list[dict]) -> list[dict]:
    rows = []
    for (device, end), temps in _windows(valid_readings(events), timedelta(minutes=3), timedelta(minutes=1)).items():
        avg = sum(temps) / len(temps)
        if len(temps) >= ALERT_MIN_READINGS and avg > ALERT_AVG_C:
            rows.append({"deviceId": device, "windowEnd": _fmt(end), "readings": len(temps),
                         "avgTempC": avg, "alertType": "COLD_ROOM_TOO_WARM"})
    return sorted(rows, key=lambda r: (r["windowEnd"], r["deviceId"]))
