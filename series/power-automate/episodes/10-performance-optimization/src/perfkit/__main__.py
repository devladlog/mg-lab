"""python -m perfkit lint <flow.json>...
python -m perfkit cost <flow.json>... [--items 1000] [--done-old 0.4]    (dry-run against a fake list)
python -m perfkit compare <slow.json> <fast.json> [--items 1000 2000 4000]"""
import argparse
import sys

from flowkit.lint import load_flow

from . import budget, rules


def lint_main(argv) -> int:
    code = 0
    for path in argv:
        findings = rules.analyze(load_flow(path))
        print(f"{path}: {len(findings)} finding(s)")
        for f in findings:
            print("  " + str(f))
        code |= any(f.level == "error" for f in findings)
    return 1 if code else 0


def cost_main(argv) -> int:
    p = argparse.ArgumentParser(prog="perfkit cost")
    p.add_argument("flows", nargs="+")
    p.add_argument("--items", type=int, default=1000)
    p.add_argument("--done-old", type=float, default=0.4)
    a = p.parse_args(argv)
    for path in a.flows:
        c = budget.measure(path, a.items, done_old_fraction=a.done_old)
        print(f"{c.name}: {c.items} items, {c.to_archive} to archive -> {c.actions} actions, {c.sharepoint_calls} SharePoint calls "
              f"(>= {c.throttle_floor_minutes:.1f} min at 600 calls/min), archived {c.archived}, run {c.status}")
    return 0


def compare_main(argv) -> int:
    p = argparse.ArgumentParser(prog="perfkit compare")
    p.add_argument("slow")
    p.add_argument("fast")
    p.add_argument("--items", type=int, nargs="+", default=[1000, 2000, 4000])
    p.add_argument("--done-old", type=float, default=0.4)
    a = p.parse_args(argv)
    print(f"{'items':>6} {'to archive':>10} | {'slow actions':>12} {'calls':>6} {'min.':>5} | {'fast actions':>12} {'calls':>6} {'min.':>5} | Low profile (10,000/day)")
    for n in a.items:
        s = budget.measure(a.slow, n, done_old_fraction=a.done_old)
        f = budget.measure(a.fast, n, done_old_fraction=a.done_old)
        verdict = ("slow OVER" if s.over() else "slow ok") + ", " + ("fast OVER" if f.over() else "fast ok")
        print(f"{n:>6} {s.to_archive:>10} | {s.actions:>12} {s.sharepoint_calls:>6} {s.throttle_floor_minutes:>5.1f} | "
              f"{f.actions:>12} {f.sharepoint_calls:>6} {f.throttle_floor_minutes:>5.1f} | {verdict}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmds = {"lint": lint_main, "cost": cost_main, "compare": compare_main}
    if not argv or argv[0] not in cmds:
        print(__doc__)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
