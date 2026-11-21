"""Failover/cutover gate over the Site Recovery REST list `replicationProtectedItems` (api-version 2025-08-01; newer versions exist).

Field names come from the REST reference on Learn: properties.replicationHealth, protectionState, testFailoverState,
lastSuccessfulTestFailoverTime, allowedOperations, providerSpecificDetails.rpoInSeconds and .lastRpoCalculatedTime.
The thresholds are our policy, not Microsoft's: RPO target 15 minutes, a successful test failover within 90 days.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Check:
    item: str
    name: str
    passed: bool
    detail: str


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_items(path: Path | str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return data["value"] if isinstance(data, dict) else data


def evaluate(items: list[dict], now: datetime, rpo_target_s: int = 900, max_test_age_days: int = 90,
             max_rpo_age_minutes: int = 60) -> list[Check]:
    checks: list[Check] = []
    for item in items:
        props = item.get("properties", {})
        name = props.get("friendlyName") or item.get("name", "?")
        detail = props.get("providerSpecificDetails") or {}

        def add(check: str, passed: bool, text: str) -> None:
            checks.append(Check(item.get("name", name), check, passed, text))

        health = props.get("replicationHealth")
        add("replication-health", health == "Normal", f"{name}: replicationHealth={health}")

        rpo, calculated = detail.get("rpoInSeconds"), parse_time(detail.get("lastRpoCalculatedTime"))
        if rpo is None:
            add("rpo", False, f"{name}: no RPO reported yet (initial replication still running?)")
        else:
            add("rpo", rpo <= rpo_target_s, f"{name}: RPO {rpo}s against a target of {rpo_target_s}s")
            fresh = calculated is not None and now - calculated <= timedelta(minutes=max_rpo_age_minutes)
            add("rpo-fresh", fresh, f"{name}: RPO calculated {calculated.isoformat() if calculated else 'never'}")

        tested = parse_time(props.get("lastSuccessfulTestFailoverTime"))
        add("test-failover-recent", tested is not None and now - tested <= timedelta(days=max_test_age_days),
            f"{name}: last successful test failover {tested.date().isoformat() if tested else 'never'} (limit {max_test_age_days} days)")

        allowed = props.get("allowedOperations") or []
        add("failover-allowed", "UnplannedFailover" in allowed and "TestFailover" in allowed,
            f"{name}: allowedOperations={','.join(allowed) or 'none'}")
    return checks


def verdict(checks: list[Check]) -> dict[str, bool]:
    """Per item: ready only if every check passed."""
    result: dict[str, bool] = {}
    for check in checks:
        result[check.item] = result.get(check.item, True) and check.passed
    return result
