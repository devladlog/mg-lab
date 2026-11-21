"""python -m d365kit check-filter "<text>" | fires --flow f.json --changed col,col --row row.json | lint f.json... | bind <set> <guid>"""
import argparse
import json
import sys
from pathlib import Path

from flowkit.lint import load_flow

from .odata import FilterError, bind, check_filter, evaluate_filter
from .triggers import fires, lint_flow, trigger_settings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="d365kit")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check-filter", help="check text pasted into a Filter rows box")
    c.add_argument("text")
    c.add_argument("--row", help="JSON file with a row: also say whether the filter passes it")
    f = sub.add_parser("fires", help="would the flow's update trigger fire for this change?")
    f.add_argument("--flow", required=True)
    f.add_argument("--changed", default="", help="comma-separated columns included in the update request")
    f.add_argument("--row", required=True, help="JSON file: the row after the save")
    l = sub.add_parser("lint", help="Dataverse trigger and lookup checks for solution flows")
    l.add_argument("flows", nargs="+")
    b = sub.add_parser("bind", help="value for a lookup column of Add a new row")
    b.add_argument("entity_set")
    b.add_argument("row_id")
    a = p.parse_args(argv)

    if a.cmd == "check-filter":
        found = check_filter(a.text)
        for x in found:
            print(x)
        if a.row:
            try:
                print("row passes the filter:", evaluate_filter(a.text, json.loads(Path(a.row).read_text(encoding="utf-8"))))
            except FilterError as e:
                print(f"ERROR   can't evaluate: {e}")
                return 1
        elif not found:
            print("OK")
        return 1 if any(x.level == "error" for x in found) else 0
    if a.cmd == "fires":
        flow = load_flow(a.flow)
        row = json.loads(Path(a.row).read_text(encoding="utf-8"))
        changed = [c for c in a.changed.split(",") if c]
        for s in trigger_settings(flow):
            print(f"{s['name']}: {'FIRES' if fires(s, row, changed) else 'does not fire'}")
        return 0
    if a.cmd == "lint":
        bad = 0
        for path in a.flows:
            found = lint_flow(load_flow(path))
            for x in found:
                print(f"{path}: {x}")
            print(f"{path}: {'OK' if not found else str(len(found)) + ' finding(s)'}")
            bad += any(x.level == "error" for x in found)
        return 1 if bad else 0
    print(bind(a.entity_set, a.row_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
