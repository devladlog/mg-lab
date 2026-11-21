"""python -m dlpkit check <flow.json|folder>... --policy P.json [--policy Q.json] [--environment dev] [--what-if http=Business]
python -m dlpkit show <policy.json>...
python -m dlpkit groups --policy P.json [--policy Q.json] <connector id>..."""
import argparse
import json
import sys
from pathlib import Path

from flowkit.lint import load_flow

from .connectors import display, norm_id
from .evaluate import connectors_of, consolidated_groups, evaluate
from .exfil import external_recipients
from .model import BLOCKED, BUSINESS, NONBUSINESS, PolicyError, group_of, load_policies, validate


def _flow_files(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*.json") if not f.name.endswith(".data.xml"))
        else:
            yield p


def check_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="dlpkit check")
    ap.add_argument("flows", nargs="+")
    ap.add_argument("--policy", action="append", required=True)
    ap.add_argument("--environment", help="environment the flow is deployed to (matches a policy's scope)")
    ap.add_argument("--what-if", action="append", default=[], metavar="CONNECTOR=GROUP",
                    help="try a classification change, e.g. http=Business")
    ap.add_argument("--allowed-domain", action="append", default=[], help="email domains that aren't external")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    a = ap.parse_args(argv)
    try:
        policies = load_policies(*a.policy)
        what_if = {}
        for w in a.what_if:
            c, _, g = w.partition("=")
            what_if[norm_id(c)] = group_of(g)
    except (PolicyError, OSError, ValueError, KeyError) as e:
        print(f"Can't read the policy: {e}")
        return 2
    bad = warned = 0
    for f in _flow_files(a.flows):
        flow = load_flow(f)
        use = connectors_of(flow)
        names = {}
        for p in policies:
            names.update(p.names)
        used = ", ".join(sorted(display(c, names) for c in use.connectors)) or "none"
        found = evaluate(use.connectors, policies, a.environment, what_if)
        if found:
            bad += 1
            print(f"SUSPENDED  {f.name}  ({used})")
            for v in found:
                print(f"           {v}")
        else:
            print(f"OK         {f.name}  ({used})")
        for n in use.not_evaluated:
            print(f"           not evaluated: {n}")
        if a.allowed_domain:
            warns, unchecked = external_recipients(flow, set(a.allowed_domain))
            for w in warns:
                warned += 1
                print(f"           {w}")
            for u in unchecked:
                print(f"           not checked: {u}")
    print(f"{bad} flow(s) would be suspended" + (f", {warned} warning(s)" if a.allowed_domain else ""))
    return 1 if bad or (a.strict and warned) else 0


def show_main(argv) -> int:
    code = 0
    for p in load_policies(*argv):
        print(f"{p.display_name}  (default group: {p.default}; scope: {p.scope_mode}"
              f"{' ' + ', '.join(p.environments) if p.environments else ''})")
        for g in (BUSINESS, NONBUSINESS, BLOCKED):
            members = sorted(display(c, p.names) for c, grp in p.groups.items() if grp == g)
            print(f"  {g:<13} {', '.join(members) if members else '-'}")
        for problem in validate(p):
            code = 1
            print(f"  ERROR {problem}")
    return code


def groups_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="dlpkit groups")
    ap.add_argument("connectors", nargs="+")
    ap.add_argument("--policy", action="append", required=True)
    a = ap.parse_args(argv)
    pols = load_policies(*a.policy)
    for i, members in enumerate(consolidated_groups([norm_id(c) for c in a.connectors], pols), 1):
        print(f"group {i}: {', '.join(members)}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmds = {"check": check_main, "show": show_main, "groups": groups_main}
    if not argv or argv[0] not in cmds:
        print(__doc__)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
