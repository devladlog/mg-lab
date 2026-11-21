"""Writes tests/asa_cases/<case>/input.json, aggregates.json and alerts.json from the reference model.

Run once (`python tests/make_asa_cases.py`) when a case changes. The files are committed; the test compares the real
Stream Analytics runtime against them. All times are in the past: the local runtime clamps events more than five minutes
in the future (see README, gotchas).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asa_reference import expected_aggregates, expected_alerts  # noqa: E402

BASE = "2026-11-20T10:{m:02d}:{s:02d}Z"
HERE = Path(__file__).parent / "asa_cases"


def ev(device, minute, second, temp, humidity=55.0, **extra):
    row = {"deviceId": device, "temperatureC": temp, "humidityPct": humidity, "observedAt": BASE.format(m=minute, s=second)}
    row.update(extra)
    return row


def steady():
    rows = []
    for minute in range(0, 3):
        for second in (5, 20, 35, 50):
            rows.append(ev("coldroom-01", minute, second, 4.0 if second % 20 else 4.5))
            rows.append(ev("coldroom-02", minute, second, 3.5))
    return rows


def warm():
    rows = []
    for minute in range(0, 6):
        for second in (10, 25, 40, 55):
            rows.append(ev("coldroom-03", minute, second, 9.0))        # sustained warm: alert
            rows.append(ev("coldroom-04", minute, second, 8.0))        # exactly 8.0: not above the threshold
        rows.append(ev("coldroom-05", minute, 30, 12.0))               # hot but only one reading a minute, 3 in a window: alert
    rows.append(ev("coldroom-06", 2, 10, 15.0))                        # two hot readings only: fewer than 3, no alert
    rows.append(ev("coldroom-06", 2, 40, 15.0))
    return sorted(rows, key=lambda r: r["observedAt"])


def malformed():
    rows = []
    for second in (5, 20, 35, 50):
        rows.append(ev("coldroom-01", 0, second, 4.0))
    rows.append(ev("coldroom-01", 0, 12, "n/a"))                       # text: dropped
    rows.append(ev("coldroom-01", 0, 14, None))                        # null: dropped
    row = ev("coldroom-01", 0, 16, 0.0)
    del row["temperatureC"]                                            # missing field: dropped
    rows.append(row)
    row = ev("coldroom-01", 0, 18, 4.0)
    del row["deviceId"]                                                # no device: dropped
    rows.append(row)
    rows.append(ev("coldroom-01", 0, 22, "5.5"))                       # numeric string: TRY_CAST accepts it
    rows.append(ev("coldroom-01", 1, 0, 6.0))                          # exactly on the minute: belongs to the window ending 10:01:00
    return sorted(rows, key=lambda r: r["observedAt"])


CASES = {"steady": steady, "warm-room": warm, "malformed": malformed}

if __name__ == "__main__":
    for name, build in CASES.items():
        folder = HERE / name
        folder.mkdir(parents=True, exist_ok=True)
        events = build()
        (folder / "input.json").write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8")
        (folder / "aggregates.json").write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in expected_aggregates(events)), encoding="utf-8")
        (folder / "alerts.json").write_text(
            "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in expected_alerts(events)), encoding="utf-8")
        print(name, len(events), "events,", len(expected_aggregates(events)), "aggregates,", len(expected_alerts(events)), "alerts")
