"""python -m formatlint lint <map.json>       -> findings (exit 1 on errors)
   python -m formatlint preview <map.json> <sample-rows.json> [--view NAME]  -> what each row would look like"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .expr import Date, FormatError
from .lint import lint_map
from .render import classes, render_column, render_view, texts


def _row_for(row: dict, fields: list[str]):
    return {k: (Date.parse(v) if k == "DueDate" and v else v) for k, v in row.items() if k in fields}


def preview(map_path: Path, rows_path: Path, view: str) -> list[dict]:
    m = json.loads(map_path.read_text(encoding="utf-8"))
    data = json.loads(rows_path.read_text(encoding="utf-8"))
    fields = m["views"][view]["fields"]
    now, me = Date.parse(data["now"]), data["me"]
    out = []
    for i, raw in enumerate(data["rows"]):
        row = _row_for(raw, fields)
        ctx = dict(me=me, now=now, row_index=i, display=raw.get("__display", {}))
        line = {"Title": raw["LinkTitle"]}
        for col, file in m["columns"].items():
            if col not in fields:
                continue
            fmt = json.loads((map_path.parent / file).read_text(encoding="utf-8"))
            try:
                node = render_column(fmt, col, row, **ctx)
            except FormatError as e:
                line[col] = f"!! {e}"
                continue
            bits = [" ".join(texts(node))] + sorted(classes(node))
            style = node.get("style", {})
            bits += [f"{k}:{v}" for k, v in style.items() if k in ("color", "width") and v]
            line[col] = " | ".join(b for b in bits if b)
        vf = m["views"][view].get("format")
        if vf:
            fmt = json.loads((map_path.parent / vf).read_text(encoding="utf-8"))
            line["row class"] = render_view(fmt, row, **ctx).get("additionalRowClass", "")
        out.append(line)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="formatlint")
    sub = p.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lint")
    lp.add_argument("map")
    pp = sub.add_parser("preview")
    pp.add_argument("map")
    pp.add_argument("rows")
    pp.add_argument("--view", default=None)
    a = p.parse_args(argv)

    if a.cmd == "lint":
        findings = lint_map(a.map)
        for f in findings:
            print(f)
        errors = sum(f.severity == "Error" for f in findings)
        warnings = len(findings) - errors
        print(f"{errors} error(s), {warnings} warning(s)" if findings else "No findings.")
        return 1 if errors else 0

    map_path = Path(a.map)
    view = a.view or next(iter(json.loads(map_path.read_text(encoding="utf-8"))["views"]))
    print(f"Preview of view '{view}'")
    for line in preview(map_path, Path(a.rows), view):
        print("- " + line.pop("Title"))
        for k, v in line.items():
            print(f"    {k:<14} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
