"""Send loop. The IoT Hub client is injected, so tests never touch the network."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol, Sequence

from .telemetry import ColdRoom, check_budget, encode, make_reading


class Client(Protocol):
    def send(self, body: bytes, content_type: str, content_encoding: str) -> None: ...
    def close(self) -> None: ...


@dataclass
class Stats:
    sent: int = 0
    failed: int = 0
    per_device: dict[str, int] = field(default_factory=dict)


def sdk_client_factory(connection_string: str) -> Client:
    """Real client: azure-iot-device (imported here so the tests do not need it)."""
    from azure.iot.device import IoTHubDeviceClient, Message

    sdk = IoTHubDeviceClient.create_from_connection_string(connection_string)
    sdk.connect()

    class _Client:
        def send(self, body: bytes, content_type: str, content_encoding: str) -> None:
            message = Message(body)
            message.content_type = content_type
            message.content_encoding = content_encoding
            sdk.send_message(message)

        def close(self) -> None:
            sdk.shutdown()

    return _Client()


def run(
    rooms: Sequence[ColdRoom],
    connection_strings: dict[str, str],
    *,
    scenario: str = "normal",
    interval_seconds: float = 5.0,
    duration_seconds: float = 300.0,
    already_sent_today: int = 0,
    client_factory: Callable[[str], Client] = sdk_client_factory,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
    seed: int = 18,
) -> Stats:
    missing = [r.device_id for r in rooms if r.device_id not in connection_strings]
    if missing:
        raise KeyError(f"no connection string for: {', '.join(missing)} (run provision first)")
    check_budget(len(rooms), interval_seconds, duration_seconds, already_sent_today=already_sent_today)

    rng = random.Random(seed)
    clients = {r.device_id: client_factory(connection_strings[r.device_id]) for r in rooms}
    stats = Stats(per_device={r.device_id: 0 for r in rooms})
    ticks = int(duration_seconds // interval_seconds) + 1
    try:
        for tick in range(ticks):
            started = clock()
            for room in rooms:
                payload = make_reading(room, started, tick, scenario, rng)
                body, ctype, cenc = encode(payload)
                try:
                    clients[room.device_id].send(body, ctype, cenc)
                except Exception:  # keep the fleet running; count the failure
                    stats.failed += 1
                else:
                    stats.sent += 1
                    stats.per_device[room.device_id] += 1
            if tick < ticks - 1:
                sleep(interval_seconds)
    finally:
        for client in clients.values():
            client.close()
    return stats
