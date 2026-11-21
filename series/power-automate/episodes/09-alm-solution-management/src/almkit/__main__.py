"""python -m almkit check <solution> [--previous <solution>] [--settings file ...] [--templates file ...]
python -m almkit diff <old> <new>
python -m almkit render-settings <template> --solution <folder> [--out file]   (values from environment variables)"""
import argparse
import json
import os
import sys

from . import checks, diff, settings
from .model import SolutionError, load_solution


def _print(findings) -> int:
    for f in findings:
        print(f)
    errors = sum(f.level == "error" for f in findings)
    print(f"{errors} error(s), {len(findings) - errors} warning(s)")
    return 1 if errors else 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="almkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("solution")
    c.add_argument("--previous")
    c.add_argument("--settings", nargs="*", default=[], help="rendered files: no ${TOKEN} allowed")
    c.add_argument("--templates", nargs="*", default=[], help="committed files: ${TOKEN} allowed")
    d = sub.add_parser("diff")
    d.add_argument("old")
    d.add_argument("new")
    r = sub.add_parser("render-settings")
    r.add_argument("template")
    r.add_argument("--solution", required=True)
    r.add_argument("--out")
    a = p.parse_args(argv)
    try:
        if a.cmd == "check":
            sol = load_solution(a.solution)
            findings = checks.check_solution(sol)
            if a.previous:
                findings += checks.check_version_bump(load_solution(a.previous), sol)
            for f, rendered in [(x, True) for x in a.settings] + [(x, False) for x in a.templates]:
                findings += checks.check_settings(sol, checks.settings_file(f), os.path.basename(f), rendered)
            return _print(findings)
        if a.cmd == "diff":
            plan = diff.plan(load_solution(a.old), load_solution(a.new))
            print("\n".join(plan.lines()))
            return 0
        sol = load_solution(a.solution)
        text = open(a.template, encoding="utf-8-sig").read()
        try:
            out = settings.render(text, os.environ)
        except settings.SettingsError as e:
            print(f"Can't render {a.template}: {e}")
            return 2
        findings = checks.check_settings(sol, json.loads(out), os.path.basename(a.template), rendered=True)
        code = _print(findings)
        if code == 0 and a.out:
            open(a.out, "w", encoding="utf-8").write(out)
            print(f"wrote {a.out}")
        return code
    except SolutionError as e:
        print(f"Can't read the solution: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
