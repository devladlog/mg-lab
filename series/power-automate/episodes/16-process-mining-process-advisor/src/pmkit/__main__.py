"""python -m pmkit generate | doctor | clean | analyze | dirty"""
import argparse
import csv
import json
import sys

from .analyze import analyze, precedence_violations
from .eventlog import COLUMNS, MAPPING, read_csv, write_csv
from .generate import CASES, generate, make_dirty
from .validate import check, clean


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pmkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write the fictional purchasing event log")
    g.add_argument("--out", required=True)
    g.add_argument("--cases", type=int, default=CASES)
    g.add_argument("--seed", type=int, default=26)
    d = sub.add_parser("dirty", help="write the same log with the defects `doctor` looks for")
    d.add_argument("--out", required=True)
    d.add_argument("--cases", type=int, default=CASES)
    d.add_argument("--seed", type=int, default=26)
    c = sub.add_parser("doctor", help="check a CSV before uploading it")
    c.add_argument("csv")
    c.add_argument("--max-mb", type=float, default=100)
    k = sub.add_parser("clean", help="repair a CSV: trim, one spelling, ISO UTC timestamps, duplicates")
    k.add_argument("csv")
    k.add_argument("--out", required=True)
    k.add_argument("--month-first", action="store_true", help="read nn/nn/yyyy as month/day (default day/month)")
    a = sub.add_parser("analyze", help="the numbers the dashboard should show")
    a.add_argument("csv")
    a.add_argument("--json", action="store_true")
    a.add_argument("--before", nargs=2, metavar=("FIRST", "THEN"), help="also list cases where THEN happened before FIRST")
    args = p.parse_args(argv)

    if args.cmd == "generate":
        write_csv(args.out, generate(args.cases, args.seed))
        print(f"wrote {args.out}")
        return 0
    if args.cmd == "dirty":
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\r\n")
            w.writerow(COLUMNS)
            w.writerows(make_dirty(generate(args.cases, args.seed)))
        print(f"wrote {args.out}")
        return 0
    if args.cmd == "doctor":
        found = check(args.csv, args.max_mb)
        for f in found:
            print(f)
        if not found:
            print("OK: mandatory columns present, ISO timestamps, no empty ids, one spelling per activity")
            print("Map on upload: " + "; ".join(f"{k} = {v}" for k, v in MAPPING.items()))
        return 1 if any(f.level == "error" for f in found) else 0
    if args.cmd == "clean":
        events, report = clean(args.csv, day_first=not args.month_first)
        write_csv(args.out, events)
        for k, v in sorted(report.items()):
            print(f"{k}: {v}")
        print(f"wrote {len(events)} rows to {args.out}")
        return 0
    events = read_csv(args.csv)
    r = analyze(events)
    if args.before:
        r["precedence_violations"] = {"rule": f"{args.before[1]} before {args.before[0]}",
                                      "cases": precedence_violations(events, *args.before)}
    if args.json:
        print(json.dumps(r, indent=2))
        return 0
    print(f"cases {r['cases']}  events {r['events']}  activities {r['activities']}  variants {r['variants']}  resources {r['resources']}")
    print(f"average case duration {r['avg_case_duration_h']} h  median {r['median_case_duration_h']} h")
    print(f"self-loop cases {r['self_loop_cases_pct']} %  loop cases {r['loop_cases_pct']} %  rework cases {r['rework_cases_pct']} %")
    print("top variants:")
    for v in r["top_variants"]:
        print(f"  {v['count']:>4} ({v['pct']:>5} %)  " + " > ".join(v["path"]))
    print("slowest transitions (mean wait, at least 20 cases):")
    for s in r["slowest_transitions"]:
        print(f"  {s['mean_wait_h']:>6} h  {s['name']}  ({s['count']} cases)")
    if "precedence_violations" in r:
        pv = r["precedence_violations"]
        print(f"{pv['rule']}: {len(pv['cases'])} case(s) {pv['cases'][:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
