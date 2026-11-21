#!/usr/bin/env python3
"""Send a burst of purchase events straight to the Service Bus topic (what API Management does in episode 7).

    python3 scripts/send_burst.py --namespace sb-mgl10-abc123 --count 60 --poison 2

Uses the Service Bus REST "Send message" call with a Microsoft Entra token from `az account get-access-token`
(you need the Azure Service Bus Data Sender role on the namespace or the topic). Every message has its own
MessageId (a GUID) and Label purchase.high, so it passes the finance-review filter. Standard library only.
"""
import argparse
import concurrent.futures
import json
import random
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

RESOURCE = "https://servicebus.azure.net"


def get_token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", RESOURCE, "--query", "accessToken", "-o", "tsv"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def make_event(n: int, rng: random.Random) -> dict:
    return {
        "eventType": "submitted",
        "purchaseRequestId": f"PR-{9000 + n}",
        "requestedBy": "alex.demo@contoso.example",
        "total": rng.randrange(5000, 20001),
        "currency": "EUR",
        "note": f"burst message {n}",
    }


def build_request(namespace: str, topic: str, token: str, event: dict, message_id: str) -> urllib.request.Request:
    broker = json.dumps({"MessageId": message_id, "Label": "purchase.high", "CorrelationId": event.get("purchaseRequestId", message_id)}, separators=(",", ":"))
    return urllib.request.Request(
        f"https://{namespace}.servicebus.windows.net/{topic}/messages",
        data=json.dumps(event).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "BrokerProperties": broker},
    )


def make_poison(n: int) -> dict:
    """Passes the gateway's label rule but not the worker's schema: the worker answers DROP and the message is not retried."""
    return {"eventType": "approved", "note": f"poison message {n}"}


def send_one(namespace: str, topic: str, token: str, n: int, seed: int, opener=urllib.request.urlopen, poison: bool = False) -> int:
    rng = random.Random(seed * 100003 + n)
    event = make_poison(n) if poison else make_event(n, rng)
    req = build_request(namespace, topic, token, event, str(uuid.UUID(int=rng.getrandbits(128), version=4)))
    try:
        with opener(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main(argv: list[str] | None = None, token_fn=get_token, opener=urllib.request.urlopen) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--namespace", required=True, help="Service Bus namespace NAME (not the host name)")
    ap.add_argument("--topic", default="purchase-events")
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--poison", type=int, default=0, help="also send this many invalid messages (the worker drops them)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1, help="same seed, same events")
    a = ap.parse_args(argv)
    if not 1 <= a.count <= 5000:
        ap.error("--count must be between 1 and 5000")
    if not 0 <= a.poison <= 100:
        ap.error("--poison must be between 0 and 100")

    token = token_fn()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs = [(n, False) for n in range(a.count)] + [(a.count + n, True) for n in range(a.poison)]
        codes = list(pool.map(lambda j: send_one(a.namespace, a.topic, token, j[0], a.seed, opener, poison=j[1]), jobs))
    ok = sum(1 for c in codes if c == 201)  # Service Bus answers 201 Created for a sent message
    print(f"sent {ok}/{len(jobs)} (201 Created, {a.poison} of them invalid on purpose); other codes: {sorted(set(codes) - {201}) or 'none'}")
    return 0 if ok == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
