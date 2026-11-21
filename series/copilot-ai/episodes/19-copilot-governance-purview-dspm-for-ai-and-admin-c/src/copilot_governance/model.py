"""Small helpers to read the tenant snapshot produced by scripts/Export-CopilotGovernanceSnapshot.ps1.

PowerShell serialises multi-valued properties either as a list or as a single string, and enums either as a string or
as a number, so every reader here is tolerant. Nothing here invents data: a missing section stays missing and the
checks report it as "not collected" instead of passing it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COPILOT_DLP_LOCATION_ID = "470f2276-e011-4e9d-a6ec-20768be3a4b0"  # Learn: New-DlpCompliancePolicy -Locations


def as_list(value: Any) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "enabled", "enable"):
        return True
    if text in ("false", "0", "no", "disabled", "disable"):
        return False
    return None


@dataclass
class Snapshot:
    raw: dict[str, Any]
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def collected_at(self) -> str:
        return str(self.raw.get("collectedAt", ""))

    def section(self, name: str) -> Any:
        """None when the collector could not read the section (see errors), [] or {} when it read an empty one."""
        return self.raw.get(name)


def load_snapshot(path: str | Path) -> Snapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("snapshot must be a JSON object")
    errors = data.get("errors") or {}
    return Snapshot(raw=data, errors={str(k): str(v) for k, v in errors.items()})
