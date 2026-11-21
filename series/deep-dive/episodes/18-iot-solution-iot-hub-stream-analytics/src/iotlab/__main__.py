"""python -m iotlab sample | budget | provision | simulate"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import provision as prov
from .simulator import run
from .telemetry import DEFAULT_ROOMS, FREE_TIER_MESSAGES_PER_DAY, SCENARIOS, QuotaExceeded, encode, estimate_daily_cost, make_reading, schedule


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iotlab")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="print telemetry messages, no network")
    sample.add_argument("--scenario", choices=SCENARIOS, default="normal")
    sample.add_argument("--count", type=int, default=5)
    sample.add_argument("--interval", type=float, default=5.0)

    budget = sub.add_parser("budget", help="what a run costs against the free-tier daily quota")
    budget.add_argument("--devices", type=int, default=len(DEFAULT_ROOMS))
    budget.add_argument("--interval", type=float, default=5.0)
    budget.add_argument("--minutes", type=float, default=20.0)

    pv = sub.add_parser("provision", help="create the demo devices with the Azure CLI (needs az login)")
    pv.add_argument("--hub", required=True)
    pv.add_argument("--file", type=Path, default=Path(prov.LOCAL_FILE))

    sim = sub.add_parser("simulate", help="send telemetry to IoT Hub (needs provision first)")
    sim.add_argument("--scenario", choices=SCENARIOS, default="normal")
    sim.add_argument("--interval", type=float, default=5.0)
    sim.add_argument("--minutes", type=float, default=10.0)
    sim.add_argument("--sent-today", type=int, default=0, help="messages already used today (portal: IoT Hub overview)")
    sim.add_argument("--file", type=Path, default=Path(prov.LOCAL_FILE))

    args = parser.parse_args(argv)

    if args.command == "sample":
        rng = random.Random(18)
        start = datetime.now(timezone.utc)
        for tick, moment in enumerate(schedule(start, args.interval, args.count)):
            for room in DEFAULT_ROOMS:
                body, ctype, _ = encode(make_reading(room, moment, tick, args.scenario, rng))
                print(body.decode("utf-8"))
        return 0

    if args.command == "budget":
        cost = estimate_daily_cost(args.devices, args.interval, args.minutes * 60)
        print(f"{cost} messages of the {FREE_TIER_MESSAGES_PER_DAY} per day on the free tier "
              f"({cost / FREE_TIER_MESSAGES_PER_DAY:.0%})")
        return 0

    if args.command == "provision":
        strings = prov.provision(args.hub, [r.device_id for r in DEFAULT_ROOMS], args.file)
        print(f"{len(strings)} devices ready, connection strings in {args.file} (not printed)")
        return 0

    strings = json.loads(args.file.read_text(encoding="utf-8"))
    try:
        stats = run(DEFAULT_ROOMS, strings, scenario=args.scenario, interval_seconds=args.interval,
                    duration_seconds=args.minutes * 60, already_sent_today=args.sent_today)
    except QuotaExceeded as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    print(f"sent {stats.sent}, failed {stats.failed}, per device {stats.per_device}")
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
