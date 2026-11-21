#!/usr/bin/env python3
"""report-lint: design and accessibility rules for a Power BI report saved as PBIR (Power BI Project).

Rules
  RL001 error    visual outside the page
  RL002 warning  two visuals overlap
  RL003 warning  position or size not on the 8 px grid
  RL004 error    data visual without alt text                     (Learn accessibility checklist)
  RL005 error    alt text longer than 250 characters              (Learn: the Alt Text box limit)
  RL006 warning  data visual without a title
  RL007 warning  tab order missing, duplicated or not in reading order (top to bottom, left to right)
  RL008 warning  hard-coded hex colour in a visual (pick theme colours so a theme change updates it)
  RL009 warning  more than --max-visuals visuals on a page          (our team rule, default 10)
  RL010 error    field that doesn't exist in the semantic model (TMDL)

Usage:
    python report_lint.py <Report folder> --model <SemanticModel/definition> [--max-visuals 10]
"""
import argparse
import json
import re
import sys
from pathlib import Path

GRID = 8
ALT_TEXT_MAX = 250
DECORATIVE = {"shape", "image", "actionButton", "textbox", "basicShape"}
HEX = re.compile(r"'#[0-9A-Fa-f]{3,8}'")


def model_fields(definition: Path):
    """{table: {column or measure names}} read from the TMDL table files."""
    fields = {}
    for f in (definition / "tables").glob("*.tmdl"):
        text = f.read_text(encoding="utf-8")
        table = re.search(r"^table\s+('(?:[^']|'')+'|\S+)", text, flags=re.M).group(1).strip("'")
        names = re.findall(r"^\t(?:column|measure)\s+('(?:[^']|'')+'|[^\s=]+)", text, flags=re.M)
        fields[table] = {n.strip("'").replace("''", "'") for n in names}
    return fields


def literal_text(container_objects, obj, prop):
    try:
        v = container_objects[obj][0]["properties"][prop]["expr"]["Literal"]["Value"]
    except (KeyError, IndexError, TypeError):
        return None
    return v[1:-1].replace("''", "'") if v.startswith("'") else v


def field_refs(node):
    """Yield (table, property) for every Column/Measure reference in a query."""
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            if kind in node and isinstance(node[kind], dict):
                e = node[kind]
                yield e["Expression"]["SourceRef"].get("Entity"), e["Property"]
        for v in node.values():
            yield from field_refs(v)
    elif isinstance(node, list):
        for x in node:
            yield from field_refs(x)


def lint(report: Path, model: Path, max_visuals=10):
    findings = []
    fields = model_fields(model)
    add = lambda rule, sev, where, msg: findings.append(
        {"rule": rule, "severity": sev, "where": where, "message": msg})

    for page_dir in sorted((report / "definition" / "pages").iterdir()):
        if not page_dir.is_dir():
            continue
        page = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
        pw, ph = page["width"], page["height"]
        visuals = []
        for vf in sorted((page_dir / "visuals").glob("*/visual.json")):
            v = json.loads(vf.read_text(encoding="utf-8"))
            visuals.append(v)
        pname = page["name"]
        if len(visuals) > max_visuals:
            add("RL009", "warning", pname, f"{len(visuals)} visuals on the page (team limit {max_visuals})")

        for v in visuals:
            where = f"{pname}/{v['name']}"
            p = v["position"]
            vt = v.get("visual", {}).get("visualType", "")
            if p["x"] < 0 or p["y"] < 0 or p["x"] + p["width"] > pw or p["y"] + p["height"] > ph:
                add("RL001", "error", where, f"outside the {pw}x{ph} page: x={p['x']} y={p['y']} "
                                             f"w={p['width']} h={p['height']}")
            off = [k for k in ("x", "y", "width", "height") if p[k] % GRID]
            if off:
                add("RL003", "warning", where, f"{', '.join(off)} not a multiple of {GRID}")
            objs = v.get("visual", {}).get("visualContainerObjects", {})
            if vt and vt not in DECORATIVE:
                alt = literal_text(objs, "general", "altText")
                if not alt:
                    add("RL004", "error", where, f"{vt} has no alt text")
                elif len(alt) > ALT_TEXT_MAX:
                    add("RL005", "error", where, f"alt text is {len(alt)} characters (max {ALT_TEXT_MAX})")
                if not literal_text(objs, "title", "text"):
                    add("RL006", "warning", where, f"{vt} has no title text")
            if HEX.search(json.dumps(v.get("visual", {}))):
                colours = sorted(set(HEX.findall(json.dumps(v.get("visual", {})))))
                add("RL008", "warning", where, f"hard-coded colour(s) {', '.join(colours)}: use theme colours")
            for table, prop in field_refs(v.get("visual", {}).get("query", {})):
                if table not in fields or prop not in fields[table]:
                    add("RL010", "error", where, f"'{table}'[{prop}] isn't in the semantic model")

        for i, a in enumerate(visuals):
            for b in visuals[i + 1:]:
                pa, pb = a["position"], b["position"]
                if (pa["x"] < pb["x"] + pb["width"] and pb["x"] < pa["x"] + pa["width"]
                        and pa["y"] < pb["y"] + pb["height"] and pb["y"] < pa["y"] + pa["height"]):
                    add("RL002", "warning", f"{pname}/{a['name']}", f"overlaps {b['name']}")

        orders = [v["position"].get("tabOrder") for v in visuals]
        if any(o is None for o in orders):
            missing = [v["name"] for v in visuals if v["position"].get("tabOrder") is None]
            add("RL007", "warning", pname, f"no tab order on {', '.join(missing)}")
        elif len(set(orders)) != len(orders):
            add("RL007", "warning", pname, "duplicated tab order values")
        else:
            reading = sorted(visuals, key=lambda v: (v["position"]["y"], v["position"]["x"]))
            by_tab = sorted(visuals, key=lambda v: v["position"]["tabOrder"])
            if [v["name"] for v in reading] != [v["name"] for v in by_tab]:
                add("RL007", "warning", pname, "tab order isn't the reading order: "
                                               + " > ".join(v["name"] for v in by_tab))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-visuals", type=int, default=10)
    a = ap.parse_args()
    findings = lint(Path(a.report), Path(a.model), a.max_visuals)
    for f in findings:
        print(f"  {f['severity'].upper():7}  {f['rule']}  {f['where']}: {f['message']}")
    errors = sum(f["severity"] == "error" for f in findings)
    print(f"{errors} error(s), {len(findings) - errors} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
