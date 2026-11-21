#!/usr/bin/env python3
"""Write the Power Query M of every table partition and every shared expression of a TMDL model to <out>/<Name>.pq, so
pq-lint (Microsoft's parser) can check it:   python extract_m.py <SemanticModel/definition> <out folder>"""
import re
import sys
import textwrap
from pathlib import Path


def dedent_block(lines):
    return textwrap.dedent("\n".join(lines)).strip() + "\n"


def extract(definition: Path) -> dict:
    out = {}
    for f in sorted((definition / "tables").glob("*.tmdl")):
        text = f.read_text(encoding="utf-8")
        name = re.search(r"^table\s+(\S.*?)\s*$", text, re.M).group(1).strip("'")
        m = re.search(r"^\t\tsource =\n((?:\t\t\t.*\n?|\n)+)", text, re.M)
        if m:
            out[name] = dedent_block(m.group(1).splitlines())
    exp = definition / "expressions.tmdl"
    if exp.exists():
        lines = exp.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            m = re.match(r"^expression\s+(\S+)\s*=\s*(.*)$", lines[i])
            if not m:
                i += 1
                continue
            name, rest = m.group(1), m.group(2)
            if rest.strip():                                   # parameter: one line
                out[name] = rest.strip() + "\n"
                i += 1
            else:                                              # function/query: indented block
                block = []
                i += 1
                while i < len(lines) and (lines[i].startswith("\t\t") or not lines[i].strip()):
                    block.append(lines[i])
                    i += 1
                out[name] = dedent_block(block)
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for name, text in extract(Path(sys.argv[1])).items():
        (out / f"{name}.pq").write_text(text, encoding="utf-8")
    print(f"wrote {len(list(out.glob('*.pq')))} query file(s) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
