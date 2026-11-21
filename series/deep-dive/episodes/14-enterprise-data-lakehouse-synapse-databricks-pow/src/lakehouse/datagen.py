"""Deterministic fictional Contoso order change feed (JSON lines). No real data anywhere."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

REGIONS = ["emea", "amer", "apac"]
CURRENCY_FOR = {"emea": "EUR", "amer": "USD", "apac": "GBP"}


def make_batch(path: str, batch_no: int, orders: int = 200, seed: int = 14) -> Path:
    """Batch 1 inserts, later batches update/delete earlier orders and add a few bad rows."""
    rng = random.Random(seed * 1000 + batch_no)
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1) + timedelta(days=7 * (batch_no - 1))
    lines = []
    seq = batch_no * 100_000
    for i in range(orders):
        region = rng.choice(REGIONS)
        seq += 1
        lines.append({"order_id": f"C-{batch_no}-{i:05d}", "op": "I", "seq": seq,
                      "customer_email": f"customer{rng.randint(1, 60)}@contoso.example",
                      "region": region, "currency": CURRENCY_FOR[region],
                      "amount": round(rng.uniform(5, 900), 2),
                      "order_ts": (start + timedelta(minutes=rng.randint(0, 7 * 24 * 60))).isoformat()})
    if batch_no > 1:
        for i in range(0, orders // 10):                      # corrections to last week's orders
            seq += 1
            lines.append({"order_id": f"C-{batch_no - 1}-{i:05d}", "op": "U" if i % 3 else "D", "seq": seq,
                          "customer_email": "customer1@contoso.example", "region": "emea", "currency": "EUR",
                          "amount": 10.0, "order_ts": start.isoformat()})
    lines.append({"order_id": "C-bad-1", "op": "I", "seq": seq + 1, "customer_email": "x@contoso.example",
                  "region": "emea", "currency": "XXX", "amount": 5.0, "order_ts": start.isoformat()})
    f = out / f"orders-{batch_no:04d}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in lines) + "\n{\"order_id\": \"C-trunc\n", encoding="utf-8")
    return f
