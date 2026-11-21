"""Command line: send | push | expect | inventory.  Secrets come from environment variables, never from arguments."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import events
import inventory
import push
import reference
import sender


def _plan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--minutes", type=int, default=10, help="minutes of sales in the plan")
    p.add_argument("--rate", type=int, default=30, help="sales per minute at the base rate")
    p.add_argument("--run-id", default="demo17", help="stamped on every event: the totals check filters on it")
    p.add_argument("--speed", type=float, default=1.0, help="10 = play ten minutes in one minute (EventTime is compressed too)")


def _plan(a: argparse.Namespace):
    return events.build_plan(seed=a.seed, minutes=a.minutes, rate_per_min=a.rate, run_id=a.run_id)


def cmd_send(a: argparse.Namespace) -> int:
    if a.dry_run:
        transport: sender.Transport = sender.NdjsonTransport(a.dry_run)
    else:
        conn = os.environ.get(sender.CONNECTION_STRING_ENV, "")
        if "EntityPath=" not in conn:
            print(f"Set {sender.CONNECTION_STRING_ENV} to the Event Hub connection string of the eventstream custom endpoint "
                  "(it must contain EntityPath=). Use --dry-run FILE to write the events to a file instead.", file=sys.stderr)
            return 2
        transport = sender.EventHubTransport(conn)
    now = datetime.now(timezone.utc)
    t0 = now if a.no_wait else sender.next_minute(now)  # live: start on a whole minute so the flash sale lands in whole KQL bins
    try:
        summary = sender.run(_plan(a), transport, t0=t0, run_id=a.run_id, speed=a.speed, realtime=not a.no_wait,
                             start_delay=(t0 - now).total_seconds())
    finally:
        transport.close()
    print("\n".join(summary.lines()))
    return 0


def cmd_push(a: argparse.Namespace) -> int:
    token = os.environ.get("PBI_ACCESS_TOKEN", "")
    if not token:
        print("Set PBI_ACCESS_TOKEN to a Power BI access token (scope Dataset.ReadWrite.All).", file=sys.stderr)
        return 2
    client = push.PushClient(token)
    plan = events.build_plan(seed=a.seed, minutes=a.minutes, rate_per_min=a.rate, run_id=a.run_id)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=a.minutes / a.speed)  # the run is already over: history, not the future
    rows = [events.to_record(s, t0, a.run_id, a.speed) for s in events.unique_sales(plan)]
    dataset_id = client.create_dataset(a.workspace_id, push.dataset_definition(a.name))
    posts = client.post_rows(a.workspace_id, dataset_id, rows, max_bytes=push.MAX_STREAMING_REQUEST_BYTES if a.streaming_tiles else None)
    print(f"dataset {dataset_id}: {len(rows)} rows in {posts} POST requests")
    return 0


def cmd_expect(a: argparse.Namespace) -> int:
    records = reference.read_ndjson(a.ndjson)
    t = reference.totals(records)
    print(" ".join(f"{k}={v}" for k, v in t.items()))
    online = reference.per_minute(records, "Online")
    print("online orders per minute:")
    for minute, value in online.items():
        print(f"  {minute}  {value:6.0f}")
    print("spike minutes (online):", ", ".join(reference.spike_minutes(online)) or "none")
    return 0


def cmd_inventory(a: argparse.Namespace) -> int:
    token = os.environ.get("PBI_ACCESS_TOKEN", "")
    if not token:
        print("Set PBI_ACCESS_TOKEN to a Power BI access token (scope Dataset.Read.All and Workspace.Read.All).", file=sys.stderr)
        return 2
    print(inventory.to_csv(inventory.find_realtime_models(push.PushClient(token).get)), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tillstream", description="Live till events for the Contoso Bikes real-time episode")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send", help="send the plan to an eventstream custom endpoint (or a file with --dry-run)")
    _plan_args(s)
    s.add_argument("--dry-run", metavar="FILE", help="write NDJSON to FILE instead of sending")
    s.add_argument("--no-wait", action="store_true", help="do not pace the sending (EventTime values are still spread over the run)")
    s.set_defaults(fn=cmd_send)

    s = sub.add_parser("push", help="legacy: create a push/streaming semantic model and post the unique events to it")
    _plan_args(s)
    s.add_argument("--workspace-id", required=True)
    s.add_argument("--name", default="TillEventsLegacy")
    s.add_argument("--streaming-tiles", action="store_true", help="keep each POST under 15 KB so streaming tiles can render it")
    s.set_defaults(fn=cmd_push)

    s = sub.add_parser("expect", help="print what the Eventhouse should answer for an NDJSON file written by send --dry-run")
    s.add_argument("ndjson")
    s.set_defaults(fn=cmd_expect)

    s = sub.add_parser("inventory", help="list push, streaming and PubNub semantic models in the workspaces you can see (CSV)")
    s.set_defaults(fn=cmd_inventory)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
