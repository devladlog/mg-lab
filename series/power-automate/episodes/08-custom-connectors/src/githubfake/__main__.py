"""python -m githubfake                    the real flow: an issue is opened, an IT request is created, GitHub gets a comment
python -m githubfake --no-defaults        draft 1: hook body without defaults (events push, form content type)
python -m githubfake --no-delete          draft 2: no delete operation, the webhook outlives the flow
python -m githubfake --no-condition       draft 3: no trigger condition, the ping event runs the flow
python -m githubfake --read-only-token    a token without the Issues permission: the comment fails after the request exists"""
import argparse
import sys

from connectorkit import load_connector

from . import scenario, variants
from flowkit import load_flow


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="githubfake", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for f in ("no-defaults", "no-delete", "no-condition", "read-only-token"):
        p.add_argument("--" + f, action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    c = load_connector(scenario.CONNECTOR_DIR)
    flow = load_flow(scenario.FLOW_PATH)
    if a.no_defaults:
        c = variants.no_body_defaults(c)
    if a.no_delete:
        c = variants.no_delete_operation(c)
    if a.no_condition:
        flow = variants.no_trigger_condition(flow)
    perms = scenario.FULL - {"issues:write"} if a.read_only_token else scenario.FULL
    w = scenario.make_world(c, flow, permissions=perms)
    w.platform.turn_on()
    w.gh.open_issue(scenario.REPO, "Laptop won't boot before a client demo", "It stops at the logo.", "alex-demo", ["hardware", "urgent"])
    w.gh.open_issue(scenario.REPO, "Need a second monitor", "For the Lisbon office.", "sam-demo", [])
    w.gh.edit_issue(scenario.REPO, 2, "Need a second monitor (27 inch)", "sam-demo")
    print(scenario.describe(w))
    print("-- the flow is turned off")
    r = w.platform.turn_off()
    print(f"unsubscribe: {'no Location header, nothing to call' if r is None else 'DELETE ' + str(r.status)}")
    w.gh.open_issue(scenario.REPO, "Printer jam, floor 2", "", "riley-demo", [])
    print(scenario.describe(w).splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
