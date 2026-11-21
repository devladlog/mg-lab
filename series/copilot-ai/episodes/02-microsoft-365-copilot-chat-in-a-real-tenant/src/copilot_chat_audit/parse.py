"""Read Copilot audit records (CSV export, JSON, or JSON lines) and normalise them.

Schema reference: https://learn.microsoft.com/office/office-365-management-api/copilot-schema and
https://learn.microsoft.com/purview/audit-copilot . Where Learn does not show a property's exact location
(AppIdentity, AgentId, AgentName), the parser looks at the top level and inside CopilotEventData.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

csv.field_size_limit(10_000_000)  # AuditData can be large

WEB_SEARCH_PLUGIN_ID = "BingWebSearch"  # AISystemPlugin.Id when Copilot used the public web via Bing (Learn)


@dataclass
class Interaction:
    record_id: str
    created: datetime | None
    user: str
    operation: str
    app_host: str
    app_identity: str
    agent_id: str
    agent_name: str
    web_search: bool
    plugins: list[str] = field(default_factory=list)
    resources: int = 0
    labelled_resources: int = 0
    models: list[str] = field(default_factory=list)
    jailbreak: bool = False
    xpia: bool = False
    dlp_deferred: int = 0
    thread_id: str = ""
    prompts: int = 0
    responses: int = 0
    client_region: str = ""


@dataclass
class LoadResult:
    interactions: list[Interaction]
    skipped_other_operations: int = 0
    skipped_unreadable: int = 0


def _ci(d: dict, *names: str) -> Any:
    """Case-insensitive lookup of the first matching key."""
    lowered = {str(k).lower(): v for k, v in d.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def to_interaction(audit: dict, fallback_user: str = "", fallback_op: str = "") -> Interaction:
    event = _ci(audit, "CopilotEventData") or {}
    if not isinstance(event, dict):
        event = {}

    def pick(*names: str) -> Any:
        found = _ci(event, *names)
        return found if found not in (None, "") else _ci(audit, *names)

    plugins = [str(_ci(p, "Id") or "") for p in _as_list(_ci(event, "AISystemPlugin")) if isinstance(p, dict)]
    resources = [r for r in _as_list(_ci(event, "AccessedResources")) if isinstance(r, dict)]
    messages = [m for m in _as_list(_ci(event, "Messages")) if isinstance(m, dict)]
    models = []
    for m in _as_list(_ci(event, "ModelTransparencyDetails")):
        if isinstance(m, dict):
            provider = _ci(m, "ModelProviderName") or ""
            name = _ci(m, "ModelName") or ""
            label = f"{provider}/{name}" if provider and name else (provider or name)
            if label:
                models.append(str(label))

    try:
        dlp = int(pick("DLPEvaluationDeferred") or 0)
    except (TypeError, ValueError):
        dlp = 0

    return Interaction(
        record_id=str(_ci(audit, "Id") or ""),
        created=_parse_time(_ci(audit, "CreationTime")),
        user=str(_ci(audit, "UserId") or fallback_user or "").lower(),
        operation=str(_ci(audit, "Operation") or fallback_op or ""),
        app_host=str(pick("AppHost") or ""),
        app_identity=str(pick("AppIdentity") or ""),
        agent_id=str(pick("AgentId") or ""),
        agent_name=str(pick("AgentName") or ""),
        web_search=WEB_SEARCH_PLUGIN_ID in plugins,
        plugins=[p for p in plugins if p],
        resources=len(resources),
        labelled_resources=sum(1 for r in resources if _ci(r, "SensitivityLabelId")),
        models=models,
        jailbreak=any(bool(_ci(m, "JailbreakDetected")) for m in messages),
        xpia=any(bool(_ci(r, "XPIADetected")) for r in resources),
        dlp_deferred=dlp,
        thread_id=str(_ci(event, "ThreadId") or ""),
        prompts=sum(1 for m in messages if _ci(m, "isPrompt")),
        responses=sum(1 for m in messages if not _ci(m, "isPrompt")),
        client_region=str(_ci(audit, "ClientRegion") or ""),
    )


def _rows_from_csv(text: str) -> Iterable[tuple[dict | None, str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        raw = _ci(row, "AuditData")
        user = _ci(row, "UserIds", "UserId") or ""
        op = _ci(row, "Operations", "Operation") or ""
        yield _loads(raw), user, op


def _loads(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _rows_from_json(items: list) -> Iterable[tuple[dict | None, str, str]]:
    for item in items:
        if not isinstance(item, dict):
            yield None, "", ""
        elif _ci(item, "AuditData") is not None:  # a Search-UnifiedAuditLog object
            yield _loads(_ci(item, "AuditData")), _ci(item, "UserIds", "UserId") or "", _ci(item, "Operations", "Operation") or ""
        else:  # already an AuditData object
            yield item, "", ""


def load_records(path: str | Path) -> LoadResult:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = _rows_from_csv(text)
    elif suffix == ".jsonl":
        rows = _rows_from_json([json.loads(line) for line in text.splitlines() if line.strip()])
    else:
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("value", [data])
        rows = _rows_from_json(data)

    result = LoadResult(interactions=[])
    for audit, user, op in rows:
        if audit is None:
            result.skipped_unreadable += 1
            continue
        operation = str(_ci(audit, "Operation") or op)
        if operation != "CopilotInteraction":
            result.skipped_other_operations += 1
            continue
        result.interactions.append(to_interaction(audit, fallback_user=user, fallback_op=op))
    return result
