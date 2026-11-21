"""Write descriptions into TMDL files as `///` lines (the TMDL description syntax), without touching anything else."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .tmdl import depth_of, find_definition, split_name


def _quote(name: str) -> str:
    if any(ch in name for ch in " .=:'"):
        return "'" + name.replace("'", "''") + "'"
    return name


def load_spec(path: str | Path) -> dict:
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("tables", "measures", "columns", "addMeasures"):
        spec.setdefault(k, {})
    return spec


def apply_to_text(text: str, spec: dict) -> tuple[str, int]:
    """Return (new text, number of descriptions added). Objects that already have a description are left alone."""
    lines = text.splitlines()
    out: list[str] = []
    table = ""
    added = 0
    in_fence = False
    has_desc = False
    for raw in lines:
        stripped = raw.strip()
        if in_fence:
            out.append(raw)
            if stripped == "```":
                in_fence = False
            continue
        if stripped.startswith("///"):
            has_desc = True
            out.append(raw)
            continue
        if stripped.endswith("```") and "=" in stripped:
            in_fence = True
        d = depth_of(raw) if stripped else -1
        text_to_add = None
        if d == 0:
            kw, _, rest = stripped.partition(" ")
            if kw.lower() == "table":
                table, _ = split_name(rest)
                text_to_add = spec.get("tables", {}).get(table)
            else:
                table = ""
        elif d == 1 and table:
            kw, _, rest = stripped.partition(" ")
            name, _ = split_name(rest)
            if kw.lower() == "measure":
                text_to_add = spec.get("measures", {}).get(f"{table}[{name}]")
            elif kw.lower() == "column":
                text_to_add = spec.get("columns", {}).get(f"{table}[{name}]")
        if text_to_add and not has_desc:
            indent = raw[: len(raw) - len(raw.lstrip())]
            out.append(f"{indent}/// {text_to_add}")
            added += 1
        if stripped:
            has_desc = False
        out.append(raw)
        if d == 0 and table and stripped.split(" ", 1)[0].lower() == "table":
            for m in spec.get("addMeasures", {}).get(table, []):
                out.append("")
                if m.get("description"):
                    out.append(f"\t/// {m['description']}")
                out.append(f"\tmeasure {_quote(m['name'])} = {m['expression']}")
                if m.get("formatString"):
                    out.append(f"\t\tformatString: {m['formatString']}")
                if m.get("displayFolder"):
                    out.append(f"\t\tdisplayFolder: {m['displayFolder']}")
                added += 1
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing, added


def apply_descriptions(model_dir: str | Path, out_dir: str | Path, spec: dict) -> int:
    """Copy the semantic model folder to out_dir and add the descriptions there. The source is never modified."""
    src_def = find_definition(model_dir)
    src_root = src_def.parent if src_def.name == "definition" else src_def
    dst_root = Path(out_dir)
    if dst_root.exists():
        raise FileExistsError(f"{dst_root} already exists")
    shutil.copytree(src_root, dst_root)
    dst_def = find_definition(dst_root)
    total = 0
    for f in sorted((dst_def / "tables").glob("*.tmdl")):
        new, n = apply_to_text(f.read_text(encoding="utf-8"), spec)
        if n:
            f.write_text(new, encoding="utf-8", newline="\n")
            total += n
    return total
