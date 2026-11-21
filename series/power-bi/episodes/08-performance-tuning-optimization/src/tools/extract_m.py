#!/usr/bin/env python3
"""Write the Power Query M of every table partition of a TMDL model to <out>/<Table>.pq (and every parameter to <out>/<Name>.pq), so pq-lint (Microsoft's
parser) can check it:   python extract_m.py <SemanticModel/definition> <out folder>"""
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lint import read_model  # noqa: E402


def extract(definition: Path):
    out = {}
    for name, t in read_model(definition).items():
        for p in t["partitions"]:
            if p["kind"] == "m":
                m = re.search(r"source =\n(.*)", p["text"], flags=re.S)
                out[name] = textwrap.dedent(m.group(1)).strip() + "\n"
    exp = definition / "expressions.tmdl"
    if exp.exists():
        for name, value in re.findall(r"^expression\s+(\S+)\s*=\s*(.+)$", exp.read_text(encoding="utf-8"), flags=re.M):
            out[name] = value.strip() + "\n"      # the parameters, so the queries' references resolve
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
