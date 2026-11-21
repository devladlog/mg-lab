#!/usr/bin/env python3
"""ir-lint: incremental refresh rules for a TMDL model folder (standard library only).

    python ir_lint.py <SemanticModel/definition> [--strict]      # --strict: warnings fail too

IR001 error   RangeStart / RangeEnd missing, or spelled with another case (Learn: reserved, case-sensitive names)
IR002 error   RangeStart / RangeEnd isn't type DateTime
IR003 error   the filter uses = on both ends (<= RangeEnd or > RangeStart): rows on the boundary land in two partitions
IR004 error   a table with a refresh policy whose partition doesn't filter with both RangeStart and RangeEnd
IR005 error   the policy itself is invalid (refresh period not shorter than the store period, unknown granularity, ...)
IR006 warning the source type has no query folding (files, web): every partition query would read the whole source
IR007 warning a step before the date filter that usually stops folding (Table.Buffer, Table.AddIndexColumn, Table.Combine, ...).
              A heuristic: confirm with View native query in Power Query
IR008 error   the date filter column isn't a column of the model as dateTime
IR009 error   detect data changes uses the same column as the filter (Learn: it shouldn't be the same column)
IR010 warning the column used to detect data changes isn't in the model (Learn: the design requires it to be persisted)
IR011 warning no polling expression: every partition of the refresh period is reloaded on every refresh
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ir_partitions import read_policy  # noqa: E402

RESERVED = ("RangeStart", "RangeEnd")
NO_FOLD_SOURCES = ("Csv.Document", "Excel.Workbook", "Folder.Files", "Folder.Contents", "SharePoint.Files", "SharePoint.Contents",
                   "Web.Contents", "Json.Document", "Xml.Tables", "Lines.FromBinary")
BREAKS_FOLDING = ("Table.Buffer", "Table.AddIndexColumn", "Table.Combine", "Table.Distinct", "Table.Skip", "Table.RemoveFirstN",
                  "Table.Sort", "Table.Repeat", "Table.FillDown", "Table.FillUp")


def finding(rule, severity, msg):
    return {"rule": rule, "severity": severity, "message": msg}


def unquote(n):
    return n.strip().strip("'")


def expressions(definition: Path) -> dict:
    out = {}
    f = definition / "expressions.tmdl"
    if f.exists():
        for m in re.finditer(r"^expression\s+(?P<n>'[^']+'|\S+)\s*=\s*(?P<v>[^\n]*)", f.read_text(encoding="utf-8"), re.M):
            out[unquote(m.group("n"))] = m.group("v")
    return out


def block(text: str, key: str, indent: int) -> str:
    m = re.search(rf"^{{0}}{key} =\n((?:{{0}}\t.*\n?|\n)+)".format("\t" * indent), text, re.M)
    return m.group(1) if m else ""


def check(definition: Path) -> list:
    out = []
    exprs = expressions(definition)
    tables = {}
    for f in sorted((definition / "tables").glob("*.tmdl")):
        t = f.read_text(encoding="utf-8")
        tables[unquote(re.search(r"^table\s+(.+?)\s*$", t, re.M).group(1))] = t
    policies = {n: read_policy(t) for n, t in tables.items()}
    ir_tables = {n: p for n, p in policies.items() if p}
    if not ir_tables:
        return out
    for r in RESERVED:
        if r not in exprs:
            wrong = [n for n in exprs if n.lower() == r.lower()]
            out.append(finding("IR001", "error", f"parameter {r} is missing" + (f" ('{wrong[0]}' has the wrong case)" if wrong else "")))
        elif 'Type="DateTime"' not in exprs[r] or "#datetime" not in exprs[r]:
            out.append(finding("IR002", "error", f"parameter {r} must be type DateTime (a #datetime value with Type=\"DateTime\")"))
    for name, pol in ir_tables.items():
        text = tables[name]
        for problem in pol.problems():
            out.append(finding("IR005", "error", f"table '{name}': {problem}"))
        part = block(text, "source", 2)
        src_expr = block(text, "sourceExpression", 2) or part
        m_code = re.sub(r"\s+", " ", part)
        if "RangeStart" not in part or "RangeEnd" not in part:
            out.append(finding("IR004", "error", f"table '{name}' has a refresh policy, but its partition doesn't filter with both RangeStart and RangeEnd"))
            continue
        ok_start = re.search(r">=\s*RangeStart|RangeStart\s*<=\s*\[", m_code)
        ok_end = re.search(r"(?<![<>=])<\s*RangeEnd|RangeEnd\s*>\s*\[", m_code)
        if not (ok_start and ok_end):
            out.append(finding("IR003", "error", f"table '{name}': the filter must be >= RangeStart and < RangeEnd (= on one side only), or rows on the boundary are loaded twice or never"))
        # source type and steps before the filter
        for s in NO_FOLD_SOURCES:
            if s in part:
                out.append(finding("IR006", "warning", f"table '{name}' reads with {s}: no query folding, every partition query reads the whole source"))
        before = m_code.split("RangeStart")[0]
        for fn in BREAKS_FOLDING:
            if fn in before:
                out.append(finding("IR007", "warning", f"table '{name}': {fn} comes before the date filter and usually stops query folding (check with View native query)"))
        # the filter column
        fm = re.search(r"\[([^\]]+)\]\s*>=\s*RangeStart|RangeStart\s*<=\s*\[([^\]]+)\]", m_code)
        cols = {}
        for c in re.finditer(r"^\tcolumn\s+(?P<n>'[^']+'|[^\s=]+)\s*\n(?P<b>(?:\t\t.*\n?)+)", text, re.M):
            s = re.search(r"sourceColumn:\s*(\S+)", c.group("b"))
            d = re.search(r"dataType:\s*(\S+)", c.group("b"))
            cols[s.group(1) if s else unquote(c.group("n"))] = (unquote(c.group("n")), d.group(1) if d else "")
        filter_col = (fm.group(1) or fm.group(2)) if fm else None
        if filter_col and (filter_col not in cols or cols[filter_col][1] != "dateTime"):
            out.append(finding("IR008", "error", f"table '{name}': the filter column '{filter_col}' is not a dateTime column of the model"))
        poll = block(text, "pollingExpression", 2)
        if not poll:
            pm = re.search(r"^\t\tpollingExpression = (.+)$", text, re.M)
            poll = pm.group(1) if pm else ""
        if not poll:
            out.append(finding("IR011", "warning", f"table '{name}' has no detect data changes expression: every refresh period partition is reloaded every time"))
        else:
            max_col = re.search(r"List\.(?:Max|Min)\([^)]*\[([^\]]+)\]", poll)
            poll_col = max_col.group(1) if max_col else None
            if poll_col and poll_col == filter_col:
                out.append(finding("IR009", "error", f"table '{name}': detect data changes uses the same column as the filter ('{poll_col}')"))
            elif poll_col and poll_col not in cols:
                out.append(finding("IR010", "warning", f"table '{name}': the column '{poll_col}' used to detect data changes isn't in the model (Learn: it has to be persisted)"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("definition")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    f = check(Path(a.definition))
    for x in f:
        print(f"  {x['severity'].upper():<7} {x['rule']}  {x['message']}")
    e, w = sum(x["severity"] == "error" for x in f), sum(x["severity"] == "warning" for x in f)
    print(f"{e} error(s), {w} warning(s)")
    return 1 if e or (a.strict and w) else 0


if __name__ == "__main__":
    sys.exit(main())
