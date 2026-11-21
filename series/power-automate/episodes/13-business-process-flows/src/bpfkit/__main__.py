"""python -m bpfkit validate <process.json>...
python -m bpfkit walk <process.json> --record record.json [--steps next,next,finish]
python -m bpfkit payload <process.json> --stage-ids ids.json --record record.json --steps next,next"""
import argparse
import json
import sys

from .engine import BpfError, Instance
from .model import Process
from .validate import validate, validate_set
from . import webapi


def _validate(argv) -> int:
    ap = argparse.ArgumentParser(prog="bpfkit validate")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    procs, bad = [], 0
    for f in a.files:
        p = Process.load(f)
        procs.append(p)
        findings = validate(p)
        print(f"{f}: {len(p.stages)} stages, {len(p.tables())} table(s)")
        for x in findings:
            print("  " + str(x))
        bad += sum(x.level == "error" for x in findings)
    for x in validate_set(procs):
        print("  " + str(x))
        bad += 1
    print("OK" if not bad else f"{bad} error(s)")
    return 1 if bad else 0


def _run(argv, payloads: bool) -> int:
    ap = argparse.ArgumentParser(prog="bpfkit")
    ap.add_argument("process")
    ap.add_argument("--record", required=True)
    ap.add_argument("--steps", default="next")
    ap.add_argument("--stage-ids")
    a = ap.parse_args(argv)
    inst = Instance(Process.load(a.process), json.load(open(a.record, encoding="utf-8")))
    ids = json.load(open(a.stage_ids, encoding="utf-8")) if a.stage_ids else None
    print(f"start: {inst.stage.name}")
    for op in a.steps.split(","):
        try:
            getattr(inst, "next" if op == "next" else op)()
        except BpfError as e:
            print(f"{op}: BLOCKED  {e}")
            return 1
        print(f"{op}: {inst.stage.name} ({inst.state})")
        if payloads and ids and op in ("next", "previous"):
            print("  PATCH " + json.dumps(webapi.move_stage(inst, ids)))
        elif payloads and op in ("abort", "finish"):
            print("  PATCH " + json.dumps(webapi.change_state(op)))
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "validate":
        return _validate(rest)
    if cmd == "walk":
        return _run(rest, False)
    if cmd == "payload":
        return _run(rest, True)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
