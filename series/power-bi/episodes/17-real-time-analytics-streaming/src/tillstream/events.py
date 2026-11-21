"""Till events for Contoso Bikes: the plan of a live sales stream.

A *plan* is a list of emissions. It is deterministic for a seed and has three things planted on purpose, so the
queries and the Power BI page have something to find:

* a flash sale: for ``flash_minutes`` minutes the online shop sells ``flash_factor`` times its normal rate of one helmet;
* duplicates: ``dup_rate`` of the events are sent twice with the same ``EventId`` (a sender that retries is at-least-once);
* late events: ``late_rate`` of the events are sent ``LATE_BY_S`` seconds after they happened.

The plan carries offsets in seconds from the start of the run. ``materialize`` turns offsets into UTC timestamps,
so the same plan can be replayed live (``t0 = now``) or in a test (``t0`` fixed).
"""
from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from catalog import CATALOG, STORES

# The JSON property names are the column names of the KQL table TillEventsRaw, in the same order.
FIELDS = ["EventId", "EventTime", "RunId", "Store", "Country", "Channel", "Till", "ProductCode", "Category",
          "Subcategory", "Quantity", "UnitPrice", "Amount", "Payment"]

LATE_BY_S = 180
_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")  # fixed, so the event ids are reproducible

STORE_WEIGHT = {"Contoso Lisboa": 30, "Contoso Porto": 20, "Contoso Madrid": 15, "Contoso Paris": 15, "Contoso Online": 20}
CATEGORY_WEIGHT = {"Bikes": 1, "Accessories": 6, "Clothing": 4}
TILL = {"Contoso Lisboa": "LIS", "Contoso Porto": "OPO", "Contoso Madrid": "MAD", "Contoso Paris": "PAR", "Contoso Online": "WEB"}
FLASH_PRODUCT = "AC-H-010"  # Helmet Sport


@dataclass(frozen=True)
class Sale:
    """One sale. ``t`` is when it happened, in seconds from the start of the run."""
    event_id: str
    t: float
    store: str
    country: str
    channel: str
    till: str
    product_code: str
    category: str
    subcategory: str
    quantity: int
    unit_price: float
    payment: str

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass(frozen=True)
class Emission:
    """One message on the wire: a sale, sent at ``send_at`` seconds from the start. A duplicate is a second emission of the same sale."""
    send_at: float
    sale: Sale
    kind: str = "normal"  # normal | duplicate | late


def _products():
    out = []
    for category, subs in CATALOG.items():
        for subcategory, items in subs.items():
            for code, _name, _color, price, _cost in items:
                out.append((code, category, subcategory, price))
    return out


def build_plan(seed: int = 42, minutes: int = 10, rate_per_min: int = 30, run_id: str = "demo17",
               flash_start_min: int = 6, flash_minutes: int = 2, flash_factor: int = 6,
               dup_rate: float = 0.02, late_rate: float = 0.01) -> list[Emission]:
    if minutes < 1 or rate_per_min < 1:
        raise ValueError("minutes and rate_per_min must be at least 1")
    rng = random.Random(seed)
    stores = {s[0]: s for s in STORES}
    store_names = list(STORE_WEIGHT)
    products = _products()
    weights = [CATEGORY_WEIGHT[p[1]] for p in products]
    flash = next(p for p in products if p[0] == FLASH_PRODUCT)

    sales: list[Sale] = []

    def add(minute: int, store: str, product) -> None:
        code, category, subcategory, price = product
        _name, country, channel = stores[store]
        online = channel == "Online"
        payment = rng.choices(["Card", "Wallet", "Cash"], [60, 25, 0 if online else 15])[0]
        quantity = rng.choices([1, 2, 3], [80, 15, 5])[0]
        sales.append(Sale(event_id=str(uuid.uuid5(_NAMESPACE, f"{run_id}/{seed}/{len(sales)}")),
                          t=round(minute * 60 + rng.uniform(0, 59.99), 2), store=store, country=country, channel=channel,
                          till=f"{TILL[store]}-{rng.randint(1, 3) if not online else 1}", product_code=code, category=category,
                          subcategory=subcategory, quantity=quantity, unit_price=price, payment=payment))

    for minute in range(minutes):
        n = max(1, round(rate_per_min * rng.uniform(0.8, 1.2)))
        for _ in range(n):
            add(minute, rng.choices(store_names, [STORE_WEIGHT[s] for s in store_names])[0], rng.choices(products, weights)[0])
        if flash_start_min <= minute < flash_start_min + flash_minutes:
            for _ in range(round(rate_per_min * 0.2 * (flash_factor - 1))):
                add(minute, "Contoso Online", flash)

    sales.sort(key=lambda s: s.t)
    # event ids were assigned in generation order; keep them (they identify the sale, not its position)
    emissions: list[Emission] = []
    for s in sales:
        r = rng.random()
        if r < late_rate:
            emissions.append(Emission(s.t + LATE_BY_S, s, "late"))
        else:
            emissions.append(Emission(s.t, s))
            if r > 1 - dup_rate:
                emissions.append(Emission(s.t + rng.uniform(1, 20), s, "duplicate"))
    emissions.sort(key=lambda e: (e.send_at, e.sale.event_id))
    return emissions


def event_time(sale: Sale, t0: datetime, speed: float = 1.0) -> datetime:
    return t0 + timedelta(seconds=sale.t / speed)


def to_record(sale: Sale, t0: datetime, run_id: str, speed: float = 1.0) -> dict:
    """The JSON object that goes on the wire. Property names equal the KQL column names."""
    when = event_time(sale, t0, speed).astimezone(timezone.utc)
    return {
        "EventId": sale.event_id,
        "EventTime": when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z",
        "RunId": run_id,
        "Store": sale.store, "Country": sale.country, "Channel": sale.channel, "Till": sale.till,
        "ProductCode": sale.product_code, "Category": sale.category, "Subcategory": sale.subcategory,
        "Quantity": sale.quantity, "UnitPrice": sale.unit_price, "Amount": sale.amount, "Payment": sale.payment,
    }


def to_json(record: dict) -> str:
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False)


def unique_sales(plan: list[Emission]) -> list[Sale]:
    """What the table should hold once duplicates are gone: one sale per EventId, in time order."""
    seen: dict[str, Sale] = {}
    for e in plan:
        seen.setdefault(e.sale.event_id, e.sale)
    return sorted(seen.values(), key=lambda s: s.t)
