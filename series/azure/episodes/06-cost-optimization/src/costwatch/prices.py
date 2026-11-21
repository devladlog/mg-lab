"""Azure Retail Prices API client: public, no sign-in, list (retail) prices.

The prices are list prices, not your negotiated rates, so treat every number as an estimate.
Things this client handles because we hit them:
  * filter values are case-sensitive (api-version 2023-01-01-preview and later)
  * at most 1,000 rows per page; follow NextPageLink
  * a 429 answer is plain text ("Too many requests ..."), with the wait in
    x-ms-ratelimit-retailprices-retry-after (seconds), observed at about 10 requests per minute
  * one filter can match several rows (Consumption, DevTestConsumption, Reservation, extra meters):
    we always add priceType eq 'Consumption' and demand exactly one row
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

API = "https://prices.azure.com/api/retail/prices"
API_VERSION = "2023-01-01-preview"
HOURS_PER_MONTH = 730  # the Azure pricing calculator's default month

Fetch = Callable[[str], tuple[int, dict[str, str], str]]


class PriceError(RuntimeError):
    """No price, or more than one: never guess."""


@dataclass(frozen=True)
class PriceQuery:
    service: str
    region: str
    sku: str
    product: str
    meter: str | None = None

    def odata_filter(self) -> str:
        def q(v: str) -> str:
            return "'" + v.replace("'", "''") + "'"

        parts = [
            f"serviceName eq {q(self.service)}",
            f"armRegionName eq {q(self.region)}",
            f"skuName eq {q(self.sku)}",
            f"productName eq {q(self.product)}",
            "priceType eq 'Consumption'",   # documented filter name; the response calls it "type"
        ]
        if self.meter:
            parts.append(f"meterName eq {q(self.meter)}")
        return " and ".join(parts)

    def key(self, currency: str) -> str:
        return f"{currency}|{self.odata_filter()}"


@dataclass(frozen=True)
class Price:
    unit_price: float
    unit: str
    currency: str
    meter: str

    def monthly(self, quantity: float = 1) -> float:
        if self.unit == "1 Hour":
            return self.unit_price * HOURS_PER_MONTH * quantity
        if self.unit == "1/Month":
            return self.unit_price * quantity
        raise PriceError(f"unit '{self.unit}' isn't a fixed monthly or hourly price ({self.meter})")


def urllib_fetch(url: str) -> tuple[int, dict[str, str], str]:
    """Default transport. Honours HTTPS_PROXY and SSL_CERT_FILE like any urllib call."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode(errors="replace")


class RetailPrices:
    def __init__(self, currency: str = "EUR", fetch: Fetch = urllib_fetch,
                 cache_file: Path | None = None, sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = 3):
        self.currency = currency
        self.fetch = fetch
        self.cache_file = cache_file
        self.sleep = sleep
        self.max_retries = max_retries
        self.requests = 0
        self.cache: dict[str, list[dict]] = {}
        if cache_file and cache_file.exists():
            self.cache = json.loads(cache_file.read_text())

    def url(self, query: PriceQuery) -> str:
        params = {"api-version": API_VERSION, "currencyCode": self.currency, "$filter": query.odata_filter()}
        return API + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    def _get(self, url: str) -> dict:
        for attempt in range(self.max_retries + 1):
            self.requests += 1
            status, headers, body = self.fetch(url)
            if status == 200:
                return json.loads(body)
            if status == 429 and attempt < self.max_retries:
                wait = headers.get("x-ms-ratelimit-retailprices-retry-after") or headers.get("retry-after") or "60"
                self.sleep(float(wait))
                continue
            raise PriceError(f"Retail Prices API answered {status}: {body[:120]}")
        raise PriceError("unreachable")

    def items(self, query: PriceQuery) -> list[dict]:
        key = query.key(self.currency)
        if key not in self.cache:
            rows, url = [], self.url(query)
            while url:
                page = self._get(url)
                rows.extend(page.get("Items", []))
                url = page.get("NextPageLink")
            self.cache[key] = rows
            if self.cache_file:
                self.cache_file.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        return self.cache[key]

    def price(self, query: PriceQuery) -> Price:
        rows = self.items(query)
        if len(rows) != 1:
            meters = sorted({f"{r.get('meterName')} ({r.get('type')})" for r in rows})
            raise PriceError(f"expected exactly 1 price for [{query.odata_filter()}], got {len(rows)}: {meters}")
        r = rows[0]
        return Price(float(r["retailPrice"]), r["unitOfMeasure"], r["currencyCode"], r["meterName"])
