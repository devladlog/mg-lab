#!/usr/bin/env python3
"""alm-check: rules for a Power BI project that is going to move through a deployment pipeline (Standard library only).

  alm_check.py check --model <SemanticModel/definition> [--report <Report folder>] [--stages stages.json]
  alm_check.py rules --model <SemanticModel/definition> --stages stages.json      # the deployment-rules sheet (markdown)
  alm_check.py diff  <old definition> <new definition>                             # changes a pipeline refuses (incremental refresh)

Every rule is something Microsoft Learn documents about deployment pipelines (see README). Exit code 1 when there is an error.

  AL001 error    a parameter that a stage rule sets isn't of type Text (parameter rules rebind with Text parameters)
  AL002 error    a stage rule names a parameter the model doesn't have (an invalid rule makes the deployment fail)
  AL003 error    rules on the Development (first) stage (rules can't be created there)
  AL004 warning  a data source address typed into the M: only a data source rule (UI) can change it per stage
  AL005 error    a data source rule on a source whose address comes from a parameter (not supported by Learn)
  AL006 warning  a table reads a dataflow with PowerPlatform.Dataflows (a Dataflow Gen2 CI/CD source isn't deployable;
                 parameters for workspace/dataflow IDs also stop autobinding)
  AL007 info     report stored as PBIR (definition folder): Learn lists PBIR as unsupported for pipelines on one page
                 and as the default format on another: test it
  AL008 warning  DirectQuery partitions and auto date/time tables in one model (not supported by pipelines)
  AL010 error    (diff) table with an incremental refresh policy renamed
  AL011 error    (diff) non-calculated column of an incremental refresh table renamed
  AL012 error    (diff) table had an incremental refresh policy and the new version has none
"""
import json
import re
import sys
from pathlib import Path

PARAM = re.compile(r'^expression\s+(?P<name>\'[^\']+\'|[A-Za-z_][\w.]*)\s*=\s*(?P<value>.+?)\s+meta\s+\[(?P<meta>.*)\]\s*$')
SOURCE_LITERAL = re.compile(r'\b(Sql\.Database|Sql\.Databases|SharePoint\.Files|SharePoint\.Contents|SharePoint\.Tables|'
                            r'AnalysisServices\.Database|OData\.Feed|Oracle\.Database|Teradata\.Database)\(\s*"([^"]+)"')
SOURCE_ANY = re.compile(r'\b(Sql\.Database|Sql\.Databases|SharePoint\.Files|SharePoint\.Contents|SharePoint\.Tables|'
                        r'AnalysisServices\.Database|OData\.Feed|Oracle\.Database|Teradata\.Database)\(\s*([A-Za-z_]\w*)')


def finding(rule, severity, message):
    return {"rule": rule, "severity": severity, "message": message}


def unquote(name: str) -> str:
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def read_model(definition: Path) -> dict:
    """Parameters, tables (text of each .tmdl) and the whole M text of the model."""
    params = {}
    exp = definition / "expressions.tmdl"
    if exp.exists():
        for line in exp.read_text(encoding="utf-8").splitlines():
            m = PARAM.match(line)
            if m and "IsParameterQuery=true" in m.group("meta").replace(" ", ""):
                t = re.search(r'Type\s*=\s*"(\w+)"', m.group("meta"))
                params[unquote(m.group("name"))] = {"type": t.group(1) if t else None, "value": m.group("value")}
    tables = {}
    for f in sorted((definition / "tables").glob("*.tmdl")) if (definition / "tables").exists() else []:
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^table\s+(\S.*?)\s*$", text, re.M)
        tables[unquote(m.group(1)) if m else f.stem] = text
    m_text = "\n".join(tables.values()) + ("\n" + exp.read_text(encoding="utf-8") if exp.exists() else "")
    return {"parameters": params, "tables": tables, "m": m_text}


def check(model: dict, report: Path | None, stages: dict | None) -> list:
    out = []
    params = model["parameters"]
    if stages:
        for st in stages["stages"]:
            rules = st.get("parameterRules") or {}
            if st["order"] == 0 and (rules or st.get("dataSourceRules")):
                out.append(finding("AL003", "error", f"stage '{st['name']}' has rules, but rules can't be created in the development stage"))
            for p in rules:
                if p not in params:
                    out.append(finding("AL002", "error", f"stage '{st['name']}': rule for parameter '{p}', which the model doesn't have"))
                elif params[p]["type"] != "Text":
                    out.append(finding("AL001", "error", f"parameter '{p}' is type {params[p]['type']}: parameter rules need Text"))
            if st.get("dataSourceRules"):
                for src in SOURCE_ANY.finditer(model["m"]):
                    if src.group(2) in params:
                        out.append(finding("AL005", "error", f"data source rule in '{st['name']}', but {src.group(1)} takes its address from parameter '{src.group(2)}'"))
                        break
    for m in SOURCE_LITERAL.finditer(model["m"]):
        out.append(finding("AL004", "warning", f"{m.group(1)} has the address typed into the M ('{m.group(2)}'): a pipeline can only change it with a data source rule in the UI; make it a parameter to set it per stage by rule"))
    if "PowerPlatform.Dataflows" in model["m"]:
        out.append(finding("AL006", "warning", "reads a dataflow with PowerPlatform.Dataflows: a model on a Dataflow Gen2 (CI/CD) source can't be deployed by a pipeline; with workspace/dataflow ID parameters, autobinding doesn't happen"))
    if "directQuery" in model["m"] and any(t.startswith("LocalDateTable_") or t.startswith("DateTableTemplate_") for t in model["tables"]):
        out.append(finding("AL008", "warning", "DirectQuery partitions and auto date/time tables in one model: not supported by deployment pipelines"))
    if report is not None and (report / "definition").is_dir():
        out.append(finding("AL007", "info", "report is PBIR (definition folder): Learn's pipeline limitations list says PBIR reports aren't supported, the PBIR article says it's the default format. Deploy one to see"))
    return out


def rules_sheet(model: dict, stages: dict) -> str:
    lines = ["| Stage | Semantic model | Rule type | Parameter | Value |", "|---|---|---|---|---|"]
    for st in stages["stages"]:
        for p, v in (st.get("parameterRules") or {}).items():
            default = model["parameters"].get(p, {}).get("value", "?")
            lines.append(f"| {st['name']} | {stages['semanticModel']} | Parameter rule | {p} | {v}  (saved value: {default}) |")
    return "\n".join(lines)


# ---------------------------------------------------------------- diff (incremental refresh tables)
def table_facts(text: str) -> dict:
    cols, calc = {}, set()
    for m in re.finditer(r"^\tcolumn\s+(?P<name>'[^']+'|[^\s=]+)(?P<calc>\s*=)?", text, re.M):
        name = unquote(m.group("name"))
        if m.group("calc"):
            calc.add(name)
            continue
        block = text[m.end():].split("\n\tcolumn ")[0].split("\n\tpartition ")[0].split("\n\tmeasure ")[0]
        s = re.search(r"sourceColumn:\s*(.+)", block)
        cols[name] = s.group(1).strip() if s else name
    return {"ir": bool(re.search(r"^\trefreshPolicy\s*$", text, re.M)), "columns": cols, "calculated": calc}


def diff(old: dict, new: dict) -> list:
    out = []
    old_t = {n: table_facts(t) for n, t in old["tables"].items()}
    new_t = {n: table_facts(t) for n, t in new["tables"].items()}
    added = {n: f for n, f in new_t.items() if n not in old_t}
    for name, f in old_t.items():
        if not f["ir"]:
            continue
        if name not in new_t:
            renamed = [a for a, af in added.items() if set(af["columns"].values()) == set(f["columns"].values())]
            if renamed:
                out.append(finding("AL010", "error", f"table '{name}' has an incremental refresh policy and is renamed to '{renamed[0]}': the deployment fails (data loss)"))
            else:
                out.append(finding("AL012", "error", f"table '{name}' had an incremental refresh policy and is gone"))
            continue
        nf = new_t[name]
        if not nf["ir"]:
            out.append(finding("AL012", "error", f"table '{name}' had an incremental refresh policy and the new version has none: the deployment fails (data loss)"))
        gone = [c for c in f["columns"] if c not in nf["columns"]]
        for c in gone:
            moved = [n for n, s in nf["columns"].items() if s == f["columns"][c] and n not in f["columns"]]
            if moved:
                out.append(finding("AL011", "error", f"table '{name}': column '{c}' is renamed to '{moved[0]}': renaming a non-calculated column of an incremental refresh table fails the deployment"))
    return out


def print_findings(items: list) -> int:
    for f in items:
        print(f"  {f['severity'].upper():7} {f['rule']}  {f['message']}")
    errors = sum(f["severity"] == "error" for f in items)
    warnings = sum(f["severity"] == "warning" for f in items)
    infos = sum(f["severity"] == "info" for f in items)
    print(f"{errors} error(s), {warnings} warning(s), {infos} info")
    return 1 if errors else 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="alm-check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--model", required=True, type=Path)
    c.add_argument("--report", type=Path)
    c.add_argument("--stages", type=Path)
    r = sub.add_parser("rules")
    r.add_argument("--model", required=True, type=Path)
    r.add_argument("--stages", required=True, type=Path)
    d = sub.add_parser("diff")
    d.add_argument("old", type=Path)
    d.add_argument("new", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        stages = json.loads(a.stages.read_text(encoding="utf-8")) if a.stages else None
        return print_findings(check(read_model(a.model), a.report, stages))
    if a.cmd == "rules":
        print(rules_sheet(read_model(a.model), json.loads(a.stages.read_text(encoding="utf-8"))))
        return 0
    return print_findings(diff(read_model(a.old), read_model(a.new)))


if __name__ == "__main__":
    sys.exit(main())
