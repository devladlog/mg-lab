"""Send a plan to a Fabric eventstream (custom endpoint, Event Hubs protocol) or to an NDJSON file.

The eventstream side is the Azure Event Hubs SDK: the *Event Hub* tab of a custom endpoint source gives a connection
string that already contains ``EntityPath``, so the producer needs nothing else. The transport is a small interface so
the pacing and the batching are tested without a network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

from events import Emission, to_json, to_record

CONNECTION_STRING_ENV = "TILLSTREAM_CONNECTION_STRING"


class Transport(Protocol):
    def send(self, payloads: list[str]) -> int:
        """Send the payloads (JSON strings). Return the number of batches used."""

    def close(self) -> None: ...


class EventHubTransport:
    """Custom endpoint of an eventstream, Event Hubs protocol. Needs ``pip install azure-eventhub``."""

    def __init__(self, connection_string: str, producer=None):
        if producer is None:
            from azure.eventhub import EventHubProducerClient  # imported here: dry runs and tests do not need the package

            producer = EventHubProducerClient.from_connection_string(connection_string)
        self._producer = producer

    def send(self, payloads: list[str]) -> int:
        from azure.eventhub import EventData

        batches = 0
        batch = self._producer.create_batch()
        for p in payloads:
            try:
                batch.add(EventData(p))
            except ValueError:  # the batch is full: send it and start the next one
                self._producer.send_batch(batch)
                batches += 1
                batch = self._producer.create_batch()
                batch.add(EventData(p))
        if len(batch) > 0:
            self._producer.send_batch(batch)
            batches += 1
        return batches

    def close(self) -> None:
        self._producer.close()


class NdjsonTransport:
    """One JSON object per line. For a dry run, and for the tests."""

    def __init__(self, path: Path | str):
        self._f = Path(path).open("w", encoding="utf-8", newline="\n")

    def send(self, payloads: list[str]) -> int:
        for p in payloads:
            self._f.write(p + "\n")
        return 1 if payloads else 0

    def close(self) -> None:
        self._f.close()


def next_minute(now: datetime) -> datetime:
    """The next whole minute. Starting the run there makes the plan's minutes line up with ``bin(EventTime, 1m)`` in KQL."""
    return now.replace(second=0, microsecond=0) + timedelta(minutes=1)


@dataclass
class Summary:
    """What the run sent. The totals are the numbers the KQL query ``totals-check.kql`` must reproduce."""
    messages: int = 0
    batches: int = 0
    unique_events: int = 0
    duplicates: int = 0
    late: int = 0
    amount: float = 0.0
    by_store: dict[str, int] = field(default_factory=dict)

    def lines(self) -> list[str]:
        return [f"messages sent      {self.messages}", f"batches            {self.batches}",
                f"unique EventId     {self.unique_events}", f"duplicates sent    {self.duplicates}",
                f"late events        {self.late}", f"amount (unique)    {self.amount:.2f}"]


def run(plan: list[Emission], transport: Transport, *, t0: datetime | None = None, run_id: str = "demo17", speed: float = 1.0,
        window_s: float = 1.0, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
        realtime: bool = True, start_delay: float = 0.0) -> Summary:
    """Send the emissions in time order, one batch per ``window_s`` of (compressed) run time.

    ``speed`` compresses time: 10 plays ten minutes of sales in one minute, and the EventTime values are compressed too.
    ``realtime=False`` sends everything at once (the timestamps are still spread over the run).
    ``start_delay`` is how many seconds from now ``t0`` lies (see ``next_minute``): the first message waits for it.
    """
    if speed <= 0 or window_s <= 0:
        raise ValueError("speed and window_s must be positive")
    t0 = t0 or datetime.now(timezone.utc)
    summary = Summary()
    seen: set[str] = set()
    start = clock() + start_delay
    i = 0
    while i < len(plan):
        window_end = plan[i].send_at / speed + window_s
        chunk = []
        while i < len(plan) and plan[i].send_at / speed < window_end:
            chunk.append(plan[i])
            i += 1
        if realtime:
            wait = chunk[-1].send_at / speed - (clock() - start)
            if wait > 0:
                sleep(wait)
        summary.batches += transport.send([to_json(to_record(e.sale, t0, run_id, speed)) for e in chunk])
        for e in chunk:
            summary.messages += 1
            if e.kind == "late":
                summary.late += 1
            if e.sale.event_id in seen:
                summary.duplicates += 1
            else:
                seen.add(e.sale.event_id)
                summary.unique_events += 1
                summary.amount = round(summary.amount + e.sale.amount, 2)
                summary.by_store[e.sale.store] = summary.by_store.get(e.sale.store, 0) + 1
    return summary
