"""python -m kbpack build | check | testset"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import docbuild, readiness, testset

HERE = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = HERE / "knowledge"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="kbpack", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Markdown sources -> .docx files, one folder per library")
    b.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    b.add_argument("--out", type=Path, required=True)

    c = sub.add_parser("check", help="check a folder of documents against the documented limits")
    c.add_argument("folder", type=Path)
    c.add_argument("--mode", choices=["site", "files"], default="site",
                   help="site = SharePoint option (URL); files = Upload files > SharePoint")
    c.add_argument("--m365-copilot", action="store_true",
                   help="the agent's tenant has a Microsoft 365 Copilot licence (200 MB instead of 7 MB)")

    t = sub.add_parser("testset", help="write the evaluation CSV(s) from the FAQ pairs")
    t.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    t.add_argument("--docs", type=Path, help="folder made by 'build'; when given, expected facts are verified")
    t.add_argument("--out", type=Path, required=True, help="output folder")

    a = p.parse_args(argv)

    if a.cmd == "build":
        made = docbuild.build_all(a.sources, a.out)
        for lib, files in made.items():
            for f in files:
                print(f"{lib}/{f.name}  {f.stat().st_size:,} bytes")
        return 0

    if a.cmd == "check":
        if not a.folder.is_dir():
            print(f"not a folder: {a.folder}", file=sys.stderr)
            return 2
        rep = readiness.check_folder(a.folder, mode=a.mode, m365_copilot=a.m365_copilot)
        print(readiness.format_report(rep))
        return 0 if rep.ok else 1

    if a.cmd == "testset":
        sources = docbuild.load_sources(a.sources)
        if a.docs:
            bad = testset.check_facts(sources, a.docs)
            if bad:
                print("\n".join(bad), file=sys.stderr)
                return 1
        general = testset.cases(sources, library="Policies") + [(q, testset.NO_ANSWER) for q in testset.OUT_OF_SCOPE]
        restricted = testset.cases(sources, library="Restricted")
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "vendor-desk-testset.csv").write_text(testset.to_csv(general), encoding="utf-8", newline="")
        (a.out / "vendor-desk-restricted.csv").write_text(testset.to_csv(restricted), encoding="utf-8", newline="")
        print(f"vendor-desk-testset.csv: {len(general)} questions")
        print(f"vendor-desk-restricted.csv: {len(restricted)} question(s) (run as a user WITHOUT access: expect no answer)")
        return 0
    return 2
