#!/usr/bin/env python3
"""contract-check: does the semantic model still match what the dataflow publishes?

The dataflow's output is a contract (dataflow/contract.json: entity, column names, order, types). A semantic model that
reads the dataflow breaks, at refresh time, when someone renames or drops a column. This checks the model's TMDL
against the contract BEFORE that happens, and checks the contract against the query files.

  DC001 error    table without a partition that reads an entity through the Dataflows connector
  DC002 error    partition reads an entity the contract doesn't list
  DC003 error    column whose sourceColumn isn't a column of the entity (renamed or dropped in the dataflow)
  DC004 error    model data type can't hold the contract type
  DC005 info     entity column the model doesn't load
  DC006 error    contract query without a .pq file, or a .pq file the contract doesn't list
  DC007 error    entity or column name with anything but letters and digits (our naming rule for the contract)
  DC008 error    workspace or dataflow ID hard-coded in a partition (use the WorkspaceId / DataflowId parameters)

Usage:
    python check_contract.py --model <SemanticModel/definition> [--contract dataflow/contract.json] [--queries dataflow/queries]
"""
import argparse
import json
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
# contract type -> model data types that hold it
COMPATIBLE = {"int64": {"int64"}, "text": {"string"}, "date": {"dateTime"}, "currency": {"decimal", "double"}}
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def unquote(name):
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def read_model(definition: Path):
    """[{name, columns: [{name, dataType, sourceColumn}], partition: M text or None}] from the TMDL table files."""
    tables = []
    for f in sorted((definition / "tables").glob("*.tmdl")):
        text = f.read_text(encoding="utf-8")
        name = unquote(re.search(r"^table\s+('(?:[^']|'')+'|\S+)", text, flags=re.M).group(1))
        columns = []
        for block in re.split(r"(?m)^\tcolumn\s+", text)[1:]:
            head = re.match(r"('(?:[^']|'')+'|\S+)", block).group(1)
            dt = re.search(r"^\t\tdataType:\s*(\S+)", block, flags=re.M)
            sc = re.search(r"^\t\tsourceColumn:\s*(.+)$", block, flags=re.M)
            columns.append({"name": unquote(head), "dataType": dt.group(1) if dt else None,
                            "sourceColumn": unquote(sc.group(1).strip().strip('"')) if sc else None})
        part = re.search(r"^\tpartition .*? = m\n\t\tmode: \w+\n\t\tsource =\n(.*)\Z", text, flags=re.M | re.S)
        tables.append({"name": name, "columns": columns, "partition": part.group(1) if part else None})
    return tables


def check(model_definition: Path, contract: dict, queries: Path):
    findings = []
    add = lambda rule, sev, where, msg: findings.append({"rule": rule, "severity": sev, "where": where, "message": msg})
    entities = contract["entities"]

    for entity, columns in entities.items():
        if not entity.isalnum():
            add("DC007", "error", entity, "entity name must be letters and digits only")
        for col in columns:
            if not col["name"].isalnum():
                add("DC007", "error", f"{entity}.{col['name']}", "column name must be letters and digits only")

    declared = set(contract["parameters"]) | set(contract["staging"]) | set(entities)
    on_disk = {p.stem for p in queries.glob("*.pq")}
    for name in sorted(declared - on_disk):
        add("DC006", "error", name, "listed in the contract but there is no .pq file")
    for name in sorted(on_disk - declared):
        add("DC006", "error", name, "a .pq file the contract doesn't list")

    for table in read_model(model_definition):
        m = table["partition"] or ""
        entity = re.search(r'entity\s*=\s*"([^"]+)"', m)
        if "PowerPlatform.Dataflows" not in m or not entity:
            add("DC001", "error", table["name"], "no partition that reads an entity through PowerPlatform.Dataflows")
            continue
        if GUID.search(m):
            add("DC008", "error", table["name"], "a workspace or dataflow ID is hard-coded in the partition")
        entity = entity.group(1)
        if entity not in entities:
            add("DC002", "error", table["name"], f"reads entity '{entity}', which the contract doesn't list")
            continue
        published = {c["name"]: c for c in entities[entity]}
        used = set()
        for col in table["columns"]:
            if col["sourceColumn"] is None:
                continue
            # Store Access adds UserPrincipalName in M: it isn't an entity column
            if table["name"] == "Store Access" and col["sourceColumn"] == "UserPrincipalName":
                continue
            src = published.get(col["sourceColumn"])
            if src is None:
                add("DC003", "error", f"{table['name']}[{col['name']}]",
                    f"sourceColumn '{col['sourceColumn']}' isn't a column of entity '{entity}'")
                continue
            used.add(src["name"])
            if col["dataType"] not in COMPATIBLE[src["type"]]:
                add("DC004", "error", f"{table['name']}[{col['name']}]",
                    f"model type {col['dataType']} can't hold the contract type {src['type']}")
        for name in published.keys() - used:
            add("DC005", "info", f"{table['name']}", f"entity column '{name}' isn't loaded by the model")
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--contract", default=str(SRC / "dataflow" / "contract.json"))
    ap.add_argument("--queries", default=str(SRC / "dataflow" / "queries"))
    a = ap.parse_args()
    contract = json.loads(Path(a.contract).read_text(encoding="utf-8"))
    findings = check(Path(a.model), contract, Path(a.queries))
    for f in findings:
        print(f"  {f['severity'].upper():7}  {f['rule']}  {f['where']}: {f['message']}")
    errors = sum(f["severity"] == "error" for f in findings)
    tables = len(contract["entities"])
    print(f"{tables} entities, {len(read_model(Path(a.model)))} model tables: {errors} error(s), {len(findings) - errors} info")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
