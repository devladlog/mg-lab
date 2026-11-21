#!/usr/bin/env python3
"""Build the Dataflow Gen2 (CI/CD) item folder from the query files, the way Fabric Git integration stores it.

    src/dataflow/queries/*.pq  +  src/dataflow/contract.json
        -> src/dataflow/ContosoBikesPrep.Dataflow/mashup.pq          one section document, one `shared` member per query
                                                  queryMetadata.json formatVersion 202502: load flags, query groups, locale
                                                  .platform          type Dataflow, display name, logicalId (zero GUID)

Part names and fields are the ones Learn documents in "Dataflow definition" (Fabric REST API). The .pq files stay the
single source of truth: edit them, regenerate, commit the folder to the Git repo a Fabric workspace is connected to.

Usage:
    python build_dataflow.py           # rewrite the item folder
    python build_dataflow.py --check   # exit 1 if the committed folder differs from the queries
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
QUERIES = SRC / "dataflow" / "queries"
CONTRACT = SRC / "dataflow" / "contract.json"
ITEM = SRC / "dataflow" / "ContosoBikesPrep.Dataflow"
NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000c07f")  # fixed, so regenerating never changes an ID
GROUPS = [("Parameters", "Values that differ per workspace or environment"),
          ("Staging", "Read and combine the source files; not published to consumers"),
          ("Output", "The entities the semantic models read (see contract.json)")]


def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def query_order(c):
    """Parameters first, then functions and staging queries, then the published entities in contract order."""
    return list(c["parameters"]) + [q for q in c["staging"] if q.startswith("fn")] \
        + [q for q in c["staging"] if not q.startswith("fn")] + list(c["entities"])


def group_of(name, c):
    return "Parameters" if name in c["parameters"] else "Staging" if name in c["staging"] else "Output"


def mashup(c):
    parts = ["section Section1;\n"]
    for name in query_order(c):
        body = (QUERIES / f"{name}.pq").read_text(encoding="utf-8").strip()
        parts.append(f"shared {name} =\n{body};\n")
    return "\n".join(parts)


def query_metadata(c):
    group_ids = {g: str(uuid.uuid5(NAMESPACE, "group:" + g)) for g, _ in GROUPS}
    return {
        "formatVersion": "202502",
        "name": c["dataflow"],
        "computeEngineSettings": {"allowFastCopy": True},
        "queryGroups": [{"id": group_ids[g], "name": g, "description": d, "order": i}
                        for i, (g, d) in enumerate(GROUPS)],
        "documentLocale": "en-US",
        "gatewayObjectId": None,
        "queriesMetadata": {
            name: {
                "queryId": str(uuid.uuid5(NAMESPACE, "query:" + name)),
                "queryName": name,
                "queryGroupId": group_ids[group_of(name, c)],
                "isHidden": False,
                # parameters and functions can't load; staging queries stay out of the consumers' navigator
                "loadEnabled": group_of(name, c) == "Output",
            } for name in query_order(c)},
        "fastCombine": False,
        "allowNativeQueries": False,
        "skipAutomaticTypeAndHeaderDetection": False,
    }


def platform(c):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Dataflow", "displayName": c["dataflow"], "description": "Prepares the Contoso Bikes exports once, for every semantic model."},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }


def files():
    c = contract()
    return {
        "mashup.pq": mashup(c),
        "queryMetadata.json": json.dumps(query_metadata(c), indent=2) + "\n",
        ".platform": json.dumps(platform(c), indent=2) + "\n",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    wanted = files()
    if a.check:
        stale = [k for k, v in wanted.items() if not (ITEM / k).exists() or (ITEM / k).read_text(encoding="utf-8") != v]
        extra = sorted(p.name for p in ITEM.iterdir() if p.name not in wanted) if ITEM.exists() else []
        for k in stale:
            print(f"out of date: {k}")
        for k in extra:
            print(f"not generated: {k}")
        print("dataflow item matches the queries" if not (stale or extra) else "dataflow item differs from the queries")
        sys.exit(1 if stale or extra else 0)
    ITEM.mkdir(parents=True, exist_ok=True)
    for k, v in wanted.items():
        (ITEM / k).write_text(v, encoding="utf-8", newline="\n")
    n = len(query_metadata(contract())["queriesMetadata"])
    print(f"wrote {len(wanted)} files, {n} queries, to {ITEM.relative_to(SRC)}")


if __name__ == "__main__":
    main()
