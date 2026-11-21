"""Small reader for the parts of TMDL that matter to Copilot.

TMDL (Tabular Model Definition Language) is indentation based: objects at one level, their properties one level
deeper, multi-line expressions one level deeper still. Descriptions are `///` lines directly above the object. Only
what the lint rules need is parsed: tables, columns, measures, their descriptions, visibility, format and
aggregation. Everything else is skipped. Spec: learn.microsoft.com/analysis-services/tmdl/tmdl-overview
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Column:
    name: str
    table: str
    description: str = ""
    hidden: bool = False
    data_type: str = ""
    summarize_by: str = ""
    is_key: bool = False
    is_calculated: bool = False


@dataclass
class Measure:
    name: str
    table: str
    description: str = ""
    hidden: bool = False
    format_string: str = ""
    expression: str = ""


@dataclass
class Table:
    name: str
    description: str = ""
    hidden: bool = False
    data_category: str = ""
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)


@dataclass
class Model:
    tables: list[Table] = field(default_factory=list)
    discourage_implicit_measures: bool = False
    path: str = ""

    def table(self, name: str) -> Table | None:
        for t in self.tables:
            if t.name.lower() == name.lower():
                return t
        return None

    def measures(self) -> list[Measure]:
        return [m for t in self.tables for m in t.measures]

    def columns(self) -> list[Column]:
        return [c for t in self.tables for c in t.columns]


def depth_of(line: str) -> int:
    """Indentation level: tabs, or groups of four spaces when no tab is used."""
    n_tab = len(line) - len(line.lstrip("\t"))
    if n_tab:
        return n_tab
    n_sp = len(line) - len(line.lstrip(" "))
    return n_sp // 4


def split_name(rest: str) -> tuple[str, str]:
    """Split `'Sales Amount' = SUM(...)` or `Margin = ...` into (name, remainder)."""
    rest = rest.strip()
    if rest.startswith("'"):
        i, name = 1, []
        while i < len(rest):
            if rest[i] == "'":
                if i + 1 < len(rest) and rest[i + 1] == "'":
                    name.append("'")
                    i += 2
                    continue
                i += 1
                break
            name.append(rest[i])
            i += 1
        return "".join(name), rest[i:].strip()
    stop = len(rest)
    for ch in (" ", "=", ":", "\t"):
        j = rest.find(ch)
        if j != -1:
            stop = min(stop, j)
    return rest[:stop], rest[stop:].strip()


def _prop(line: str) -> tuple[str, str]:
    s = line.strip()
    if ":" in s:
        k, v = s.split(":", 1)
        return k.strip().lower(), v.strip().strip('"')
    return s.lower(), "true"


def parse_table_text(text: str) -> list[Table]:
    tables: list[Table] = []
    lines = text.splitlines()
    pending_desc: list[str] = []
    table: Table | None = None
    obj: Table | Column | Measure | None = None
    obj_kind = ""
    in_fence = False
    for raw in lines:
        if in_fence:
            if raw.strip() == "```":
                in_fence = False
            continue
        if not raw.strip():
            continue
        stripped = raw.strip()
        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            continue
        d = depth_of(raw)
        if stripped.endswith("```") and "=" in stripped:
            in_fence = True
        if d == 0:
            obj, obj_kind = None, ""
            kw, _, rest = stripped.partition(" ")
            if kw.lower() == "table":
                name, _ = split_name(rest)
                table = Table(name=name, description=" ".join(pending_desc))
                tables.append(table)
                obj, obj_kind = table, "table"
            else:
                table = None
            pending_desc = []
            continue
        if table is None:
            pending_desc = []
            continue
        if d == 1:
            kw, _, rest = stripped.partition(" ")
            kw = kw.lower()
            name, remainder = split_name(rest)
            if kw == "measure":
                m = Measure(name=name, table=table.name, description=" ".join(pending_desc))
                if remainder.startswith("="):
                    m.expression = remainder[1:].strip()
                table.measures.append(m)
                obj, obj_kind = m, "measure"
            elif kw == "column":
                c = Column(name=name, table=table.name, description=" ".join(pending_desc),
                           is_calculated=remainder.startswith("="))
                table.columns.append(c)
                obj, obj_kind = c, "column"
            else:
                obj, obj_kind = None, ""
                # table level properties sit at depth 1 as well
                key, val = _prop(stripped)
                if key == "ishidden":
                    table.hidden = True
                elif key == "datacategory":
                    table.data_category = val
            pending_desc = []
            continue
        if d == 2 and obj is not None:
            key, val = _prop(stripped)
            if isinstance(obj, Column):
                if key == "ishidden":
                    obj.hidden = val.lower() != "false"
                elif key == "datatype":
                    obj.data_type = val
                elif key == "summarizeby":
                    obj.summarize_by = val.lower()
                elif key == "iskey":
                    obj.is_key = val.lower() != "false"
            elif isinstance(obj, Measure):
                if key == "ishidden":
                    obj.hidden = val.lower() != "false"
                elif key == "formatstring":
                    obj.format_string = val
        pending_desc = []
    return tables


def find_definition(path: str | Path) -> Path:
    p = Path(path)
    if (p / "definition").is_dir():
        return p / "definition"
    if (p / "tables").is_dir():
        return p
    for cand in p.glob("*.SemanticModel/definition"):
        return cand
    raise FileNotFoundError(f"No TMDL definition folder (with tables/) under {p}")


def load_model(path: str | Path) -> Model:
    d = find_definition(path)
    model = Model(path=str(d))
    mf = d / "model.tmdl"
    if mf.exists():
        for line in mf.read_text(encoding="utf-8").splitlines():
            if line.strip().lower() == "discourageimplicitmeasures":
                model.discourage_implicit_measures = True
    for f in sorted((d / "tables").glob("*.tmdl")):
        model.tables.extend(parse_table_text(f.read_text(encoding="utf-8")))
    return model
