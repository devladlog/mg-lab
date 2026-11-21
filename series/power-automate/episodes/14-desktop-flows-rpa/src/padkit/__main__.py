"""python -m padkit lint <flow.robin.txt> --contract <contract.json> [--mode attended|unattended]
python -m padkit contract <cloud flow.json> --contract <contract.json>"""
import argparse
import json
import sys

from .contract import check_cloud_flow, load_contract
from .lint import lint_script


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("lint", "contract"):
        print(__doc__)
        return 2
    ap = argparse.ArgumentParser(prog=f"padkit {argv[0]}")
    ap.add_argument("file")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--mode", default="attended", choices=["attended", "unattended"])
    a = ap.parse_args(argv[1:])
    contract = load_contract(a.contract)
    if argv[0] == "lint":
        findings = lint_script(open(a.file, encoding="utf-8").read(), contract, a.mode)
    else:
        findings = check_cloud_flow(json.load(open(a.file, encoding="utf-8-sig")), contract)
    for f in findings:
        print(f)
    errors = sum(f.level == "error" for f in findings)
    print("OK" if not findings else f"{errors} error(s), {len(findings) - errors} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
