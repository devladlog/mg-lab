"""Lint column and view formats against the rules on Microsoft Learn that the JSON schema can't check:
allowed style properties, Excel-style expressions, field references vs. view fields, link protocols."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .expr import FormatError, field_refs, to_ast

COLUMN_SCHEMA = "https://developer.microsoft.com/json-schemas/sp/v2/column-formatting.schema.json"
VIEW_SCHEMAS = {
    "https://developer.microsoft.com/json-schemas/sp/view-formatting.schema.json",
    "https://developer.microsoft.com/json-schemas/sp/v2/view-formatting.schema.json",
}

# Formatting syntax reference (Microsoft Learn): elmType, attributes and style names that are allowed.
ELM_TYPES = {"div", "span", "a", "img", "svg", "path", "button", "p", "filepreview"}
ATTRIBUTES = {"href", "rel", "src", "class", "target", "title", "role", "iconName", "d", "aria", "data-interception",
              "viewBox", "preserveAspectRatio", "draggable"}
STYLES = set("""
background-color fill background-image border border-bottom border-bottom-color border-bottom-style border-bottom-width
border-color border-left border-left-color border-left-style border-left-width border-right border-right-color
border-right-style border-right-width border-style border-top border-top-color border-top-style border-top-width
border-width outline outline-color outline-style outline-width border-bottom-left-radius border-bottom-right-radius
border-radius border-top-left-radius border-top-right-radius box-decoration-break box-shadow box-sizing overflow-x
overflow-y overflow-style rotation rotation-point opacity cursor height max-height max-width min-height min-width width
flex-grow flex-shrink flex-flow flex-direction flex-wrap flex justify-content align-items box-align box-direction
box-flex box-flex-group box-lines box-ordinal-group box-orient box-pack font font-family font-size font-style
font-variant font-weight font-size-adjust font-stretch grid-columns grid-rows margin margin-bottom margin-left
margin-right margin-top column-count column-fill column-gap column-rule column-rule-color column-rule-style
column-rule-width column-span column-width columns padding padding-bottom padding-left padding-right padding-top bottom
clear clip display left overflow position right top visibility z-index border-collapse border-spacing caption-side
empty-cells table-layout color direction letter-spacing line-height text-align text-decoration text-indent
text-transform unicode-bidi vertical-align white-space word-spacing hanging-punctuation punctuation-trim
text-align-last text-justify text-outline text-overflow text-shadow text-wrap word-break word-wrap stroke fill-opacity
--inline-editor-border-width --inline-editor-border-style --inline-editor-border-radius --inline-editor-border-color
-webkit-line-clamp object-fit transform
""".split())
LINK_PROTOCOLS = ("http://", "https://", "mailto:", "tel:")


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    message: str

    def __str__(self):
        return f"{self.severity.upper():7} {self.rule}  {self.file}: {self.message}"


def _expressions(elm: dict, where: str = ""):
    """Yield (location, value) for every value that may hold an expression, walking children."""
    if "txtContent" in elm:
        yield f"{where}txtContent", elm["txtContent"]
    for k, v in elm.get("attributes", {}).items():
        yield f"{where}attributes.{k}", v
    for k, v in elm.get("style", {}).items():
        yield f"{where}style.{k}", v
    for i, c in enumerate(elm.get("children", [])):
        yield from _expressions(c, f"{where}children[{i}].")


def _elements(elm: dict):
    yield elm
    for c in elm.get("children", []):
        yield from _elements(c)


def _leftmost(ast):
    while isinstance(ast, dict) and ast.get("operator") == "+" and ast.get("operands"):
        ast = ast["operands"][0]
    return ast


def lint_format(fmt: dict, name: str, kind: str, view_fields: dict[str, list[str]], column: str | None = None) -> list[Finding]:
    """kind: 'column' or 'view'. view_fields: views where this format is shown -> their field names."""
    out: list[Finding] = []
    add = lambda rule, sev, msg: out.append(Finding(rule, sev, name, msg))

    schema = fmt.get("$schema")
    if kind == "column" and schema != COLUMN_SCHEMA:
        add("FL001", "Error", f"$schema should be {COLUMN_SCHEMA}")
    if kind == "view" and schema not in VIEW_SCHEMAS:
        add("FL001", "Error", "$schema should be a view-formatting schema")
    if kind == "view" and "rowFormatter" in fmt and "additionalRowClass" in fmt:
        add("FL010", "Warning", "additionalRowClass is ignored when a rowFormatter is present")
    if fmt.get("debugMode"):
        add("FL009", "Warning", "debugMode is on; remove it before publishing")

    roots = [fmt] if kind == "column" else [fmt["rowFormatter"]] if "rowFormatter" in fmt else []
    values = []
    if kind == "view" and "additionalRowClass" in fmt:
        values.append(("additionalRowClass", fmt["additionalRowClass"]))
    for root in roots:
        for e in _elements(root):
            if e.get("elmType", "div") not in ELM_TYPES:
                add("FL002", "Error", f"elmType '{e.get('elmType')}' isn't allowed")
            for a in e.get("attributes", {}):
                if a not in ATTRIBUTES and not a.startswith("aria-"):
                    add("FL003", "Error", f"attribute '{a}' isn't allowed")
            for s in e.get("style", {}):
                if s not in STYLES:
                    add("FL004", "Error", f"style '{s}' isn't allowed" + (" (float is no longer supported)" if s == "float" else ""))
        values += list(_expressions(root))

    refs: set[str] = set()
    for where, v in values:
        try:
            ast = to_ast(v)
        except FormatError as e:
            add("FL005", "Error", f"{where}: {e}")
            continue
        refs |= field_refs(ast)
        if where.endswith("attributes.href"):
            first = _leftmost(ast)
            if isinstance(first, str) and not first.startswith(("[$", "@")) and not first.lower().startswith(LINK_PROTOCOLS):
                add("FL008", "Error", f"{where}: links must start with http://, https://, mailto: or tel:")

    if kind == "view" and "@currentField" in refs:
        add("FL007", "Warning", "@currentField in a view format always means the Title field; use [$InternalName]")
        refs.discard("@currentField")
    refs = {column if r == "@currentField" else r for r in refs}
    for view, fields in view_fields.items():
        missing = sorted(r for r in refs if r and r not in fields)
        for m in missing:
            add("FL006", "Error", f"reads [${m}] but view '{view}' doesn't include it (references only work for fields in the same view)")
    return out


def lint_map(map_path: str | Path) -> list[Finding]:
    """Lint every format listed in map.json against the views it will be shown in."""
    map_path = Path(map_path)
    m = json.loads(map_path.read_text(encoding="utf-8"))
    base = map_path.parent
    views = m["views"]
    findings: list[Finding] = []
    for column, file in m.get("columns", {}).items():
        fmt = json.loads((base / file).read_text(encoding="utf-8"))
        shown_in = {v: d["fields"] for v, d in views.items() if column in d["fields"]}
        findings += lint_format(fmt, Path(file).name, "column", shown_in, column)
    for view, d in views.items():
        if d.get("format"):
            fmt = json.loads((base / d["format"]).read_text(encoding="utf-8"))
            findings += lint_format(fmt, Path(d["format"]).name, "view", {view: d["fields"]})
    return findings


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
