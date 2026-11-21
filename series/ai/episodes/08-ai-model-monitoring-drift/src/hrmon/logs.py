"""Read the triage telemetry back from Log Analytics (workspace-based Application Insights: table AppTraces)."""
from __future__ import annotations

from datetime import timedelta

from .telemetry import PREFIX, check_window

FEATURES = ["lang", "length", "category", "urgency", "needs_human", "model"]


def records_query(windows: list[str]) -> str:
    """One query for both windows; counting happens in Python so local and cloud records share one code path."""
    labels = ", ".join(f'"{check_window(w)}"' for w in windows)
    cols = ",\n    ".join(f'{f} = tostring(Properties["{PREFIX}{f}"])' for f in FEATURES)
    return (
        "AppTraces\n"
        '| where Message in ("triage", "quality")\n'
        f'| extend window = tostring(Properties["{PREFIX}window"])\n'
        f"| where window in ({labels})\n"
        f"| project TimeGenerated, Message, window,\n    {cols},\n"
        f'    golden_accuracy = todouble(Properties["{PREFIX}golden_accuracy"])\n'
        "| order by TimeGenerated asc\n"
        "| take 10000"
    )


def fetch(client, workspace_id: str, windows: list[str], lookback: timedelta = timedelta(days=1)) -> list[dict]:
    """Rows as dicts shaped like the local JSON lines records ({"message", "hr_window", "hr_<feature>"...})."""
    from azure.monitor.query import LogsQueryStatus

    response = client.query_workspace(workspace_id, records_query(windows), timespan=lookback)
    if response.status != LogsQueryStatus.SUCCESS:
        err = getattr(response, "partial_error", None)
        raise RuntimeError(f"partial result from Log Analytics: {getattr(err, 'message', err)}")
    table = response.tables[0]
    names = [c if isinstance(c, str) else c.name for c in table.columns]
    out = []
    for row in table.rows:
        r = dict(zip(names, row))
        rec = {"message": r["Message"], f"{PREFIX}window": r["window"]}
        for f in FEATURES:
            if r.get(f) not in (None, ""):
                rec[f"{PREFIX}{f}"] = r[f]
        if r.get("golden_accuracy") is not None:
            rec[f"{PREFIX}golden_accuracy"] = r["golden_accuracy"]
        out.append(rec)
    return out
