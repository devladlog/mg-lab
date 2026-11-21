"""python -m dvlab provision | import | report   (add --fake to run against the in-memory stand-in)

provision: table + columns + lookup to Account + alternate key, inside a solution; waits for the key index.
import:    CSV -> upsert by alternate key in $batch requests of N (idempotent: run it twice, nothing duplicates).
report:    high-budget requests, paged with odata.maxpagesize, with formatted values.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from . import schema
from .batch import BatchItem
from .client import DataverseClient, DataverseError
from .keys import KeyValueError, key_segment

FAKE_URL = "https://contoso-dev.crm4.dynamics.com"


def make_client(args) -> DataverseClient:
    if args.fake:
        import requests
        from .fake import FakeDataverse
        fake = FakeDataverse(throttle_every=args.throttle_every, retry_after=1)
        session = requests.Session()
        session.mount("https://", fake)
        client = DataverseClient(FAKE_URL, lambda: "fake-token", session=session, solution=args.solution,
                                 sleep=lambda s: None)
        client.fake = fake  # type: ignore[attr-defined]
        return client
    from .auth import token_provider
    env = args.env_url or os.environ["DATAVERSE_URL"]
    return DataverseClient(env, token_provider(env), solution=args.solution)


def provision(client: DataverseClient, out=print) -> None:
    if client.table_exists(schema.TABLE):
        out(f"table {schema.TABLE} already exists - skipping create")
    else:
        client.create_table(schema.project_request_table())
        out(f"created table {schema.TABLE_SCHEMA} (UserOwned, change tracking on)")
        for col in schema.extra_columns():
            client.add_column(schema.TABLE, col)
            out(f"  + column {col['SchemaName']:<22} {col['AttributeType']}")
        client.create_relationship(schema.account_relationship())
        out("  + lookup mgl_CustomerAccountId -> account (delete: RemoveLink)")
        client.create_key(schema.TABLE, schema.request_code_key())
        out(f"  + alternate key {schema.KEY_SCHEMA} on {schema.KEY_COLUMNS}")
    client.wait_for_key(schema.TABLE, schema.KEY_SCHEMA, on_poll=lambda s: out(f"  key index status: {s}"))
    out("ready: upsert by mgl_requestcode is safe now")


def _row_to_body(row: Dict[str, str]) -> Dict[str, object]:
    body: Dict[str, object] = {
        "mgl_name": row["name"],
        "mgl_budget": float(Decimal(row["budget"])),
        "mgl_priority": schema.PRIORITY[row["priority"]],
    }
    if row.get("due_date"):
        body["mgl_duedate"] = row["due_date"]
    return body


def import_csv(client: DataverseClient, path: Path, batch_size: int = 100, out=print) -> Dict[str, int]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    stats = {"rows": len(rows), "sent": 0, "ok": 0, "rejected_locally": 0, "failed": 0, "distinct": 0}
    items: List[BatchItem] = []
    codes: List[str] = []
    ok_codes: set = set()

    def flush():
        if not items:
            return
        # No change set: each row stands alone; continue-on-error so one bad row doesn't stop the rest.
        results = client.batch(items, changeset=False, continue_on_error=True)
        for code, res in zip(codes, results):
            if res.status < 300:
                stats["ok"] += 1
                ok_codes.add(code)
            else:
                stats["failed"] += 1
                msg = res.body.get("error", {}).get("message") if isinstance(res.body, dict) else res.body
                out(f"  FAILED {code}: HTTP {res.status} {msg}")
        stats["sent"] += len(items)
        items.clear()
        codes.clear()

    for row in rows:
        code = row["request_code"]
        try:
            url = f"{schema.ENTITY_SET}{key_segment({'mgl_requestcode': code})}"
        except KeyValueError as e:
            stats["rejected_locally"] += 1
            out(f"  SKIPPED {code!r}: {e}")
            continue
        items.append(BatchItem("PATCH", url, _row_to_body(row)))
        codes.append(code)
        if len(items) == batch_size:
            flush()
    flush()
    stats["distinct"] = len(ok_codes)
    out(f"{stats['ok']}/{stats['rows']} rows upserted into {stats['distinct']} records, $batch of {batch_size} "
        f"({stats['failed']} failed on the server, {stats['rejected_locally']} rejected before sending)")
    return stats


def report(client: DataverseClient, min_budget: float = 50000, page_size: int = 5, out=print) -> int:
    total = 0
    pages = client.query(schema.ENTITY_SET,
                         select=["mgl_requestcode", "mgl_name", "mgl_budget", "mgl_priority"],
                         filter=f"mgl_budget ge {min_budget:g}",
                         orderby="mgl_requestcode asc", page_size=page_size)
    for n, page in enumerate(pages, start=1):
        out(f"page {n}: {len(page)} rows")
        for r in page:
            prio = r.get("mgl_priority@OData.Community.Display.V1.FormattedValue") or _prio_label(r.get("mgl_priority"))
            out(f"  {r['mgl_requestcode']:<8} {r['mgl_name'][:32]:<32} {r['mgl_budget']:>12,.2f}  {prio}")
        total += len(page)
    out(f"{total} requests with budget >= {min_budget:,.0f}")
    return total


def _prio_label(value: Optional[int]) -> str:
    return next((k for k, v in schema.PRIORITY.items() if v == value), "")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="dvlab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["provision", "import", "report", "all"])
    p.add_argument("--fake", action="store_true", help="run against the in-memory stand-in (no tenant)")
    p.add_argument("--env-url", help="https://<org>.crm.dynamics.com (or DATAVERSE_URL)")
    p.add_argument("--solution", default="MGLabDataverse", help="unique name of the solution to create components in")
    p.add_argument("--csv", type=Path, default=Path(__file__).resolve().parents[2] / "sample" / "project-requests.csv")
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--page-size", type=int, default=5)
    p.add_argument("--throttle-every", type=int, default=0, help="fake only: answer every Nth request with 429")
    args = p.parse_args(argv)

    client = make_client(args)
    try:
        if args.fake and args.command in ("import", "report"):   # the fake starts empty on every run
            provision(client, out=lambda s: None)
            if args.command == "report":
                import_csv(client, args.csv, args.batch_size, out=lambda s: None)
        if args.command in ("provision", "all"):
            provision(client)
        if args.command in ("import", "all"):
            import_csv(client, args.csv, args.batch_size)
        if args.command in ("report", "all"):
            report(client, page_size=args.page_size)
    except DataverseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if client.retries_done:
        print(f"(waited out {client.retries_done} HTTP 429 responses using Retry-After)")
    return 0
