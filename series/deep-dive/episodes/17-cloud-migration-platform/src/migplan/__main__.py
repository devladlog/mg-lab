"""python -m migplan check | plan | csv | gate"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import drgate, inventory, migrate_csv, readiness, sizing, waves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="migplan")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "plan", "csv"):
        p = sub.add_parser(name)
        p.add_argument("inventory", type=Path)
        p.add_argument("--landing-zone", action="append", default=[], help="Azure address space to check on-premises IPs against (repeatable)")
    sub.choices["check"].add_argument("--comfort", type=float, default=None)
    sub.choices["plan"].add_argument("--max-wave-size", type=int, default=8)
    sub.choices["csv"].add_argument("--out", type=Path, required=True)
    gate = sub.add_parser("gate")
    gate.add_argument("items", type=Path, help="JSON from `az rest` on replicationProtectedItems (array or {value: [...]})")
    gate.add_argument("--rpo-seconds", type=int, default=900)
    gate.add_argument("--max-test-age-days", type=int, default=90)

    args = parser.parse_args(argv)

    if args.command == "gate":
        checks = drgate.evaluate(drgate.load_items(args.items), datetime.now(timezone.utc), args.rpo_seconds, args.max_test_age_days)
        for c in checks:
            print(f"{'PASS' if c.passed else 'FAIL'}  {c.name:<22} {c.detail}")
        ok = all(drgate.verdict(checks).values()) if checks else False
        print("READY" if ok else "NOT READY")
        return 0 if ok else 1

    inv = inventory.load(args.inventory)
    findings = readiness.check_inventory(inv, tuple(args.landing_zone))

    if args.command == "check":
        for f in findings:
            print(f"{f.severity.upper():<8} {f.server:<14} {f.code:<28} {f.message}")
        print()
        for server in inv.servers:
            r = sizing.recommend(server, args.comfort)
            target = f"{r.sku.name} ({r.sku.vcpus} vCPU, {r.sku.memory_gib} GiB)" if r.sku else "-"
            print(f"{server.name:<14} {r.mode:<12} {target:<34} {r.note}")
        return 1 if any(f.severity == "blocker" for f in findings) else 0

    if args.command == "plan":
        plan = waves.plan_waves(inv, findings, args.max_wave_size)
        print("foundation (before wave 1):", ", ".join(plan.foundation) or "-")
        for w in plan.waves:
            print(f"{w.name:<8} [{w.criticality}] {', '.join(w.servers)}" + "".join(f"\n         note: {n}" for n in w.notes))
        if plan.blocked:
            print("blocked until fixed:", ", ".join(plan.blocked))
        for w in plan.warnings:
            print("warning:", w)
        return 0

    ready = readiness.importable(inv, findings)
    migrate_csv.write(ready, args.out)
    print(f"{len(ready)} of {len(inv.servers)} servers written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
