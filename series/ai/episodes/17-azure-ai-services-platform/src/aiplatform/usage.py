"""Who called what, from Azure Monitor platform metrics (no extra resource needed): calls and errors per API, latency,
and the billable units Learn lists for the services this resource served."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .endpoints import check_resource_id
from .http import ARM_SCOPE, Api

METRICS_API = "2019-07-01"     # Learn: multi-dimensional metric values need 2019-07-01 or later
PER_API = ("TotalCalls", "TotalErrors", "ClientErrors", "ServerErrors")
BILLABLE = ("ProcessedTextRecords", "TextCharactersTranslated", "ContentSafetyTextAnalyzeRequestCount")


def _series(body: dict, key: str) -> dict[str, float]:
    """Metric name -> {dimension value -> total}. Sums every data point of a time series."""
    out: dict[str, dict] = {}
    for m in body.get("value", []):
        name = m["name"]["value"]
        d = out.setdefault(name, {})
        for ts in m.get("timeseries", []):
            dim = next((v["value"] for v in ts.get("metadatavalues", []) if v["name"]["value"].lower() == "apiname"), "(all)")
            vals = [pt.get(key) for pt in ts.get("data", []) if pt.get(key) is not None]
            if vals:
                d[dim] = d.get(dim, 0) + (sum(vals) if key == "total" else sum(vals) / len(vals))
    return out


def query(api: Api, resource_id: str, minutes: int = 60, now: datetime | None = None) -> dict:
    rid = check_resource_id(resource_id)
    end = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    span = f"{(end - timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    url = f"https://management.azure.com{rid}/providers/Microsoft.Insights/metrics?api-version={METRICS_API}"

    def get(names, agg, flt=None):
        p = {"metricnames": ",".join(names), "timespan": span, "interval": "PT1M", "aggregation": agg}
        if flt:
            p["$filter"] = flt
        r = api.call("GET", url, ARM_SCOPE, params=p)
        if not r.ok:
            raise RuntimeError(f"Metrics query failed (HTTP {r.status}): {r.error_code() or r.error}")
        return r.body

    per_api = _series(get(PER_API, "Total", "ApiName eq '*'"), "total")
    latency = _series(get(["Latency"], "Average", "ApiName eq '*'"), "average").get("Latency", {})
    billable = _series(get(BILLABLE, "Total"), "total")
    return {"minutes": minutes, "per_api": per_api, "latency": latency, "billable": billable}


def render(u: dict) -> str:
    apis = sorted({a for m in u["per_api"].values() for a in m} | set(u["latency"]))
    lines = [f"Last {u['minutes']} minutes", f"{'ApiName':<34} {'calls':>7} {'errors':>7} {'4xx':>5} {'5xx':>5} {'avg ms':>8}"]
    g = lambda m, a: int(u["per_api"].get(m, {}).get(a, 0))
    for a in apis:
        lat = u["latency"].get(a)
        lines.append(f"{a:<34} {g('TotalCalls', a):>7} {g('TotalErrors', a):>7} {g('ClientErrors', a):>5} {g('ServerErrors', a):>5} {('%.0f' % lat) if lat is not None else '-':>8}")
    if not apis:
        lines.append("(no data points: metrics arrive with a delay, run again in a few minutes)")
    for m in BILLABLE:
        tot = sum(u["billable"].get(m, {}).values())
        if tot:
            lines.append(f"{m}: {int(tot)}")
    return "\n".join(lines)
