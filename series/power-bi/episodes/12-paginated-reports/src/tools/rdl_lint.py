#!/usr/bin/env python3
"""Checks a paginated report (.rdl): the schema first, then the things that bite on the first export.

  python3 rdl_lint.py ../report/ContosoStoreStatement.rdl [--schema ../../tests/schemas/reportdefinition-2016-01.xsd]

RL000 error    not valid against the RDL 2016/01 schema (Microsoft's XSD, vendored in tests/schemas)
RL001 error    body width + left and right margin is wider than the page: every page is followed by a blank page
RL002 warning  a tablix header row that doesn't repeat on new pages (RepeatOnNewPage + KeepWithGroup)
RL003 error    a query parameter in the DAX without a QueryParameter bound to a report parameter that exists
RL004 error    credentials or a dataset id inside the connection string (the file would carry a secret or a tenant id)
RL005 warning  no "Page n of m" in the page footer
RL006 error    an expression uses Fields!X.Value without a Field X in the dataset
RL008 error    a size (Width, Height, Top, Left, margins, page size) that is not a number with a unit, like 6.5inin
RL007 info     groups without a page break (fine, but then stores share pages)
Exit code 1 when there is an error. Units are converted to inches.
"""
import re
import sys
from pathlib import Path

from lxml import etree

NS = {"r": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"}
DEFAULT_XSD = Path(__file__).resolve().parents[2] / "tests" / "schemas" / "reportdefinition-2016-01.xsd"
UNIT = {"in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4, "pt": 1 / 72, "pc": 1 / 6}


def inches(text):
    m = re.fullmatch(r"\s*([0-9.]+)\s*(in|cm|mm|pt|pc)\s*", text or "")
    return float(m.group(1)) * UNIT[m.group(2)] if m else None


def lint(path, xsd=DEFAULT_XSD):
    out = []

    def add(code, level, msg):
        out.append((code, level, msg))

    doc = etree.parse(str(path))
    schema = etree.XMLSchema(etree.parse(str(xsd)))
    if not schema.validate(doc):
        for e in list(schema.error_log)[:5]:
            add("RL000", "error", f"line {e.line}: {e.message[:200]}")
        return out
    q = lambda node, p: node.xpath(p, namespaces=NS)

    sizes = "Width Height Top Left PageWidth PageHeight LeftMargin RightMargin TopMargin BottomMargin".split()
    for el in q(doc, "|".join(f"//r:{s}" for s in sizes)):
        if len(el) == 0 and inches(el.text) is None and not (el.text or "").startswith("="):
            add("RL008", "error", f"line {el.sourceline}: {etree.QName(el).localname} = '{el.text}' is not a number with a unit")

    for sec in q(doc, "//r:ReportSection"):
        body_w = inches(q(sec, "r:Width")[0].text)
        page = q(sec, "r:Page")[0]
        get = lambda tag: inches((q(page, f"r:{tag}") or [None])[0].text if q(page, f"r:{tag}") else None) or 0.0
        page_w, left, right = get("PageWidth"), get("LeftMargin"), get("RightMargin")
        if body_w is None or page_w == 0:
            add("RL001", "error", "body Width or PageWidth missing or not a number with a unit")
        elif body_w + left + right > page_w + 1e-9:
            add("RL001", "error", f"body {body_w:.2f}in + margins {left + right:.2f}in = {body_w + left + right:.2f}in is wider than the page {page_w:.2f}in")
        foot = " ".join(q(page, "r:PageFooter//r:Value/text()"))
        if "Globals!PageNumber" not in foot:
            add("RL005", "warning", "no Globals!PageNumber in the page footer")

    for tx in q(doc, "//r:Tablix"):
        name = tx.get("Name")
        rows = q(tx, "r:TablixBody/r:TablixRows/r:TablixRow")
        members = q(tx, "r:TablixRowHierarchy//r:TablixMember")
        static = [m for m in members if not q(m, "r:Group")]
        if len(rows) > 1 and not any(q(m, "r:RepeatOnNewPage") and q(m, "r:RepeatOnNewPage")[0].text == "true" and q(m, "r:KeepWithGroup") for m in static):
            add("RL002", "warning", f"tablix {name}: no header row repeats on new pages")
        groups = [m for m in members if q(m, "r:Group") and q(m, "r:Group/r:GroupExpressions")]
        if groups and not any(q(g, "r:Group/r:PageBreak") for g in groups):
            add("RL007", "info", f"tablix {name}: no group has a page break")

    for ds in q(doc, "//r:DataSource"):
        cs = " ".join(q(ds, "r:ConnectionProperties/r:ConnectString/text()"))
        if re.search(r"(password|pwd|user id|uid)\s*=", cs, re.I):
            add("RL004", "error", f"data source {ds.get('Name')}: credentials in the connection string")
        if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", cs, re.I):
            add("RL004", "error", f"data source {ds.get('Name')}: a GUID in the connection string; use workspace and model names")

    params = set(q(doc, "//r:ReportParameters/r:ReportParameter/@Name"))
    for ds in q(doc, "//r:DataSet"):
        text = " ".join(q(ds, "r:Query/r:CommandText/text()"))
        wanted = set(re.findall(r"(?<![\w\"'\[])@(\w+)", text))
        bound = {}
        for qp in q(ds, "r:Query/r:QueryParameters/r:QueryParameter"):
            bound[qp.get("Name").lstrip("@")] = " ".join(qp.xpath("r:Value/text()", namespaces=NS))
        for p in sorted(wanted):
            if p not in bound:
                add("RL003", "error", f"dataset {ds.get('Name')}: @{p} in the query has no QueryParameter")
            elif not (m := re.search(r"Parameters!(\w+)\.Value", bound[p])) or m.group(1) not in params:
                add("RL003", "error", f"dataset {ds.get('Name')}: @{p} is not bound to an existing report parameter")
        for p in sorted(set(bound) - wanted):
            add("RL003", "warning", f"dataset {ds.get('Name')}: QueryParameter {p} is not used in the query")
        fields = set(q(ds, "r:Fields/r:Field/@Name"))
        used = set(re.findall(r"Fields!(\w+)\.Value", etree.tostring(doc).decode("utf-8")))
        for f in sorted(used - fields):
            add("RL006", "error", f"expression uses Fields!{f}.Value, dataset {ds.get('Name')} has no such field")
    return out


def main(argv):
    if not argv or argv[0].startswith("-"):
        print("usage: rdl_lint.py <file.rdl> [--schema <xsd>]", file=sys.stderr)
        return 2
    xsd = argv[argv.index("--schema") + 1] if "--schema" in argv else DEFAULT_XSD
    res = lint(argv[0], xsd)
    for code, level, msg in res:
        print(f"{code} {level}: {msg}")
    e = sum(1 for r in res if r[1] == "error"); w = sum(1 for r in res if r[1] == "warning"); i = sum(1 for r in res if r[1] == "info")
    print(f"{e} error(s), {w} warning(s), {i} info(s)")
    return 1 if e else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
