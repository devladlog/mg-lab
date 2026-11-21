"""Find the push semantic models you still run, before real-time streaming is retired.

Uses two documented calls: Groups GetGroups (the workspaces the caller can see) and Datasets GetDatasetsInGroup. A dataset that
accepts rows (``addRowsAPIEnabled`` true) is a push model; the push/streaming hybrid that Azure Stream Analytics creates is one too.
Not verified: whether a pure streaming model (history off) is returned by GetDatasetsInGroup at all. Learn lists its content
provider as ``RealTimeInStreamingMode``, so that value is reported when the API returns it.
"""
from __future__ import annotations

import csv
import io
from typing import Callable

REALTIME_PROVIDERS = {"RealTimeInPushMode", "RealTimeInStreamingMode", "RealTimeInPubNubMode"}
COLUMNS = ["workspace", "workspaceId", "dataset", "datasetId", "configuredBy", "createdDate", "kind"]


def classify(dataset: dict) -> str | None:
    """'push', 'streaming', 'pubnub' or None (not a real-time model)."""
    provider = dataset.get("ContentProviderType") or dataset.get("contentProviderType")
    if provider == "RealTimeInStreamingMode":
        return "streaming"
    if provider == "RealTimeInPubNubMode":
        return "pubnub"
    if provider == "RealTimeInPushMode" or dataset.get("addRowsAPIEnabled") is True:
        return "push"
    return None


def find_realtime_models(get: Callable[[str], dict]) -> list[dict]:
    """``get`` takes a path such as ``/v1.0/myorg/groups`` and returns the parsed JSON."""
    found = []
    for ws in get("/v1.0/myorg/groups").get("value", []):
        for ds in get(f"/v1.0/myorg/groups/{ws['id']}/datasets").get("value", []):
            kind = classify(ds)
            if kind:
                found.append({"workspace": ws.get("name", ""), "workspaceId": ws["id"], "dataset": ds.get("name", ""),
                              "datasetId": ds["id"], "configuredBy": ds.get("configuredBy", ""),
                              "createdDate": ds.get("createdDate", ""), "kind": kind})
    return sorted(found, key=lambda r: (r["workspace"], r["dataset"]))


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()
