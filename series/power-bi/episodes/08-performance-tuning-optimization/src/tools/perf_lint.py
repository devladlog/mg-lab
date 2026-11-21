#!/usr/bin/env python3
"""perf-lint: finds the model and report design choices Microsoft's guidance says make Power BI slow, in the files.

It reads a semantic model saved as TMDL (and optionally the PBIR reports and a column profile of the data). It runs no
DAX and measures nothing: it tells you where to look first. Real timings come from Performance Analyzer.

  PF001 warning  auto date/time table in the model                         (Learn: Auto date/time guidance)
  PF002 warning  bi-directional relationship (info when it is a security filter: RLS needs it)
                                                                           (Learn: Bi-directional relationship guidance)
  PF003 warning  DAX calculated column on a table loaded by Power Query    (Learn: Data reduction, Preference for custom columns)
  PF004 warning  date/time column with a time part, in a table that isn't the date table
                                                                           (Learn: Model relationships, DateTime columns)
  PF005 warning  nearly unique column in an Import table (needs --profile) (Learn: Data reduction, Optimize column data types)
  PF006 warning  text column that is only a prefix plus digits (needs --profile)
                                                                           (Learn: Optimize column data types)
  PF007 warning  FILTER over a whole table as a CALCULATE filter argument  (Learn: Avoid using FILTER as a filter argument)
  PF008 warning  IFERROR / ISERROR, or / with a measure as denominator     (Learn: DIVIDE function vs. divide operator)
  PF009 warning  the same CALCULATE written twice in one measure           (Learn: Use variables to improve your DAX formulas)
  PF010 warning  more visuals on a page than --max-visuals                 (Learn: Optimization guide; the number is OUR policy)
  PF011 warning  hidden column nothing uses: no measure, relationship, sort, security role or visual
                                                                           (Learn: Data reduction, Remove unnecessary columns)

Usage:
    python perf_lint.py --model <SemanticModel/definition> [--report <Report folder> ...]
                        [--profile profile.json --profile-side before] [--max-visuals 10] [--strict] [--json] [--brief]
Exit code 1 when there are warnings and --strict is given, or errors (none today); 2 on bad input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

NAME = r"('(?:[^']|'')+'|[^\s=\[\]']+)"


def unq(n):
    return n[1:-1].replace("''", "'") if n.startswith("'") else n


# ------------------------------------------------------------------------------------------- TMDL reading
def read_model(definition: Path):
    tables = {}
    for f in sorted((definition / "tables").glob("*.tmdl")):
        lines = f.read_text(encoding="utf-8").split("\n")
        t = {"name": None, "columns": [], "measures": [], "partitions": [], "category": None, "hidden": False}
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(rf"table\s+{NAME}", line)
            if m:
                t["name"] = unq(m.group(1))
            elif line.startswith("\t") and not line.startswith("\t\t"):
                s = line.strip()
                if s.startswith("dataCategory:"):
                    t["category"] = s.split(":", 1)[1].strip()
                elif s == "isHidden":
                    t["hidden"] = True
                elif s.startswith("column "):
                    c = {"name": None, "type": None, "hidden": False, "key": False, "format": "", "source": None,
                         "expression": None, "sortBy": None}
                    mm = re.match(rf"column\s+{NAME}\s*(?:=\s*(.*))?$", s)
                    c["name"] = unq(mm.group(1))
                    c["expression"] = mm.group(2)
                    i += 1
                    while i < len(lines) and lines[i].startswith("\t\t"):
                        p = lines[i].strip()
                        if p.startswith("dataType:"): c["type"] = p.split(":", 1)[1].strip()
                        elif p == "isHidden": c["hidden"] = True
                        elif p == "isKey": c["key"] = True
                        elif p.startswith("formatString:"): c["format"] = p.split(":", 1)[1].strip()
                        elif p.startswith("sourceColumn:"): c["source"] = p.split(":", 1)[1].strip().strip("[]")
                        elif p.startswith("sortByColumn:"): c["sortBy"] = unq(p.split(":", 1)[1].strip())
                        i += 1
                    t["columns"].append(c)
                    continue
                elif s.startswith("measure "):
                    mm = re.match(rf"measure\s+{NAME}\s*=\s*(.*)$", s)
                    expr = [mm.group(2)] if mm.group(2) else []
                    i += 1
                    while i < len(lines) and lines[i].startswith("\t\t\t"):
                        expr.append(lines[i].strip())
                        i += 1
                    t["measures"].append({"name": unq(mm.group(1)), "expression": "\n".join(expr)})
                    while i < len(lines) and lines[i].startswith("\t\t"):
                        i += 1
                    continue
                elif s.startswith("partition "):
                    mm = re.match(rf"partition\s+{NAME}\s*=\s*(\w+)", s)
                    i += 1
                    body = []
                    while i < len(lines) and (lines[i].startswith("\t\t") or not lines[i].strip()):
                        body.append(lines[i])
                        i += 1
                    t["partitions"].append({"kind": mm.group(2), "text": "\n".join(body)})
                    continue
            i += 1
        tables[t["name"]] = t
    return tables


def read_relationships(definition: Path):
    path = definition / "relationships.tmdl"
    out = []
    if not path.exists():
        return out
    for block in re.split(r"\n(?=relationship )", path.read_text(encoding="utf-8")):
        m = re.match(r"relationship\s+(.+)", block)
        if not m:
            continue
        props = dict(re.findall(r"^\t(\w+):\s*(.+)$", block, flags=re.M))
        frm = re.match(rf"{NAME}\.{NAME}$", props["fromColumn"])
        to = re.match(rf"{NAME}\.{NAME}$", props["toColumn"])
        out.append({"name": unq(m.group(1).strip()), "from": (unq(frm.group(1)), unq(frm.group(2))),
                    "to": (unq(to.group(1)), unq(to.group(2))), "props": props})
    return out


def read_roles(definition: Path):
    d = definition / "roles"
    return "\n".join(f.read_text(encoding="utf-8") for f in d.glob("*.tmdl")) if d.exists() else ""


# ---------------------------------------------------------------------------------------- DAX text helpers
def mask(expr):
    """Same length, with the insides of strings and comments blanked, so parentheses inside them don't count."""
    out, i = [], 0
    while i < len(expr):
        c = expr[i]
        if c == '"':
            j = i + 1
            while j < len(expr) and not (expr[j] == '"' and expr[j + 1:j + 2] != '"'):
                j += 2 if expr[j] == '"' else 1
            out.append('"' + " " * (j - i - 1) + '"')
            i = j + 1
        elif expr.startswith("//", i) or expr.startswith("--", i):
            j = expr.find("\n", i)
            j = len(expr) if j < 0 else j
            out.append(" " * (j - i))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def calls(expr, func):
    """[(start, end, [argument text])] for every FUNC( ... ) in expr, arguments split on top-level commas."""
    masked, found = mask(expr), []
    for m in re.finditer(rf"\b{func}\s*\(", masked, flags=re.I):
        depth, args, start, i = 1, [], m.end(), m.end()
        while i < len(masked) and depth:
            ch = masked[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "," and depth == 1:
                args.append(expr[start:i])
                start = i + 1
            i += 1
        args.append(expr[start:i])
        found.append((m.start(), i + 1, [a.strip() for a in args]))
    return found


def squash(text):
    return re.sub(r"\s+", "", text).lower()


# ----------------------------------------------------------------------------------------------- the rules
def lint(model: Path, reports=(), profile=None, max_visuals=10):
    tables, rels, roles = read_model(model), read_relationships(model), read_roles(model)
    findings = []
    add = lambda rule, sev, where, msg: findings.append({"rule": rule, "severity": sev, "where": where, "message": msg})
    measure_text = "\n".join(m["expression"] for t in tables.values() for m in t["measures"])
    calc_text = "\n".join(c["expression"] or "" for t in tables.values() for c in t["columns"])
    all_dax = measure_text + "\n" + calc_text + "\n" + roles

    used_by_visual = set()
    for r in reports:
        for vf in Path(r).rglob("visual.json"):
            for tbl, prop in re.findall(r'"Entity":\s*"([^"]+)"\s*\}\s*\}\s*,\s*"Property":\s*"([^"]+)"', vf.read_text(encoding="utf-8")):
                used_by_visual.add((tbl, prop))

    for t in tables.values():
        loaded_by_m = any(p["kind"] == "m" for p in t["partitions"])
        calculated = [p for p in t["partitions"] if p["kind"] == "calculated"]
        # PF001
        if re.match(r"(LocalDateTable|DateTableTemplate)_", t["name"]) and any("calendar" in p["text"].lower() for p in calculated):
            add("PF001", "warning", t["name"], "auto date/time table: a hidden calculated table per date column. "
                "Turn Auto date/time off (File > Options > Current File > Time intelligence) and use the Date table")
        for c in t["columns"]:
            where = f"{t['name']}[{c['name']}]"
            # PF003
            if c["expression"] is not None and loaded_by_m:
                add("PF003", "warning", where, "DAX calculated column on a table Power Query loads: compute it in "
                    "Power Query (or the source) so it compresses better and doesn't wait for the refresh to finish")
            # PF004
            if c["type"] == "dateTime" and t["category"] != "Time" and re.search(r"h{1,2}[:.]?m|ss|AM/PM", c["format"], flags=re.I):
                add("PF004", "warning", where, "date/time with a time part: nearly every value is different. Keep the "
                    "date (and the hour, if reports need it) in separate low-cardinality columns")
            # PF005 / PF006 (profile)
            stat = (profile or {}).get(c["source"] or "")
            if stat and t["partitions"] and loaded_by_m:
                if stat["uniqueness"] >= 0.5 and not c["key"]:
                    add("PF005", "warning", where, f"{stat['distinct']:,} distinct values in a table of "
                        f"{round(stat['distinct'] / stat['uniqueness']):,} rows: a dictionary almost as big as the column")
                if c["type"] == "string" and stat.get("prefixed_number"):
                    add("PF006", "warning", where, "text that is a prefix plus digits: strip the prefix, load a whole number")
            # PF011
            if c["hidden"] and not c["key"] and c["expression"] is None and t["name"] in tables and loaded_by_m:
                ref = re.compile(r"(?:'%s'|\b%s)\s*\[%s\]" % (re.escape(t["name"]), re.escape(t["name"]), re.escape(c["name"])))
                in_rel = any((t["name"], c["name"]) in (r["from"], r["to"]) for r in rels)
                sorted_by = any(o["sortBy"] == c["name"] for o in t["columns"])
                if not (ref.search(all_dax) or in_rel or sorted_by or (t["name"], c["name"]) in used_by_visual):
                    add("PF011", "warning", where, "hidden and unused: no measure, relationship, sort, role or visual "
                        "refers to it. Remove it in Power Query")
        for m in t["measures"]:
            where = f"{t['name']}[{m['name']}]"
            expr = m["expression"]
            # PF007
            for _, _, args in calls(expr, "CALCULATE"):
                for a in args[1:]:
                    f = re.match(r"FILTER\s*\(\s*(.+)", a, flags=re.S | re.I)
                    if f and re.match(rf"{NAME}\s*,", f.group(1)):
                        add("PF007", "warning", where, "FILTER over a whole table as a CALCULATE filter: use a Boolean "
                            "filter ('Table'[Column] = value, with KEEPFILTERS if existing filters must stay). FILTER is "
                            "right when the condition needs a measure or several columns")
            # PF008
            masked = mask(expr)
            if re.search(r"\b(IFERROR|ISERROR)\s*\(", masked, flags=re.I):
                add("PF008", "warning", where, "IFERROR/ISERROR hides every error and costs time: DIVIDE handles the "
                    "division by zero, and an error elsewhere should show")
            elif re.search(r"\]\s*/\s*(\[|\w+\()", masked) and not re.search(r"\bDIVIDE\b", masked, flags=re.I):
                add("PF008", "warning", where, "'/' with a measure or expression as denominator: use DIVIDE (BLANK on zero)")
            # PF009
            if not re.search(r"\bVAR\b", masked, flags=re.I):
                seen = {}
                for s, e, _ in calls(expr, "CALCULATE"):
                    seen.setdefault(squash(expr[s:e]), 0)
                    seen[squash(expr[s:e])] += 1
                if any(n > 1 for n in seen.values()):
                    add("PF009", "warning", where, "the same CALCULATE appears more than once: put it in a VAR and use it twice")

    # PF002
    for r in rels:
        if r["props"].get("crossFilteringBehavior") == "bothDirections":
            secure = r["props"].get("securityFilteringBehavior") == "bothDirections"
            add("PF002", "info" if secure else "warning", r["name"],
                "bi-directional, used as a security filter: keep it, it is what row-level security needs" if secure else
                "bi-directional filtering costs query time and can confuse users: use a single direction, a visual filter "
                "'is not blank' for slicers with data, or CROSSFILTER inside the one measure that needs it")
    # PF010
    for r in reports:
        for page in sorted((Path(r) / "definition" / "pages").glob("*/page.json")):
            n = len(list((page.parent / "visuals").glob("*/visual.json")))
            if n > max_visuals:
                add("PF010", "warning", f"{Path(r).name}/{page.parent.name}",
                    f"{n} visuals on the page (our limit {max_visuals}): every visual sends its own query. Move detail to "
                    "a drillthrough or tooltip page")
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--report", action="append", default=[])
    ap.add_argument("--profile")
    ap.add_argument("--profile-side", default="before")
    ap.add_argument("--max-visuals", type=int, default=10)
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--brief", action="store_true", help="one short line per finding (the text before the first colon)")
    a = ap.parse_args()
    if not Path(a.model, "tables").is_dir():
        print(f"{a.model}: no tables folder; pass the SemanticModel/definition folder", file=sys.stderr)
        sys.exit(2)
    profile = None
    if a.profile:
        profile = json.loads(Path(a.profile).read_text(encoding="utf-8"))[a.profile_side]["columns"]
    findings = lint(Path(a.model), a.report, profile, a.max_visuals)
    if a.json:
        print(json.dumps(findings, indent=2))
    else:
        for f in findings:
            text = f["message"].split(":")[0] if a.brief else f["message"]
            print(f"  {f['severity'].upper():7} {f['rule']}  {f['where']}: {text}")
        warn = sum(f["severity"] == "warning" for f in findings)
        print(f"{warn} warning(s), {len(findings) - warn} info")
    warn = any(f["severity"] == "warning" for f in findings)
    sys.exit(1 if (warn and a.strict) else 0)


if __name__ == "__main__":
    main()
