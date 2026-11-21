"""Burst test through the gateway: watch the per-team token budget, 429s and Retry-After live.

    export APIM_SUBSCRIPTION_KEY=<key of the "hr-bot" subscription>
    python -m aoai_gateway.smoke --gateway https://<apim>.azure-api.net --deployment chat --requests 12

Retries are off by default here (--max-retries 0) so you see every 429 the gateway returns; production code keeps
the SDK default (2) and does NOT add its own retry loop on top.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

from .client import make_gateway_client
from .errors import classify_exception
from .usage import CONSUMED, REMAINING, Ledger, gateway_headers

PROMPT = [{"role": "user", "content": "Reply with the single word OK."}]


@dataclass
class Row:
    n: int
    status: int
    kind: str
    total_tokens: int | None = None
    remaining: int | None = None
    consumed: int | None = None
    retry_after_s: float | None = None

    def __str__(self) -> str:
        if self.status == 200:
            return (f"#{self.n:02d}  200  ok          tokens={self.total_tokens}"
                    f"  gateway-consumed={self.consumed}  remaining-this-minute={self.remaining}")
        ra = f"  retry-after={self.retry_after_s:g}s" if self.retry_after_s is not None else ""
        return f"#{self.n:02d}  {self.status}  {self.kind:<11}{ra}"


def run_burst(client: Any, deployment: str, requests: int, ledger: Ledger, feature: str = "smoke",
              max_completion_tokens: int = 256) -> list[Row]:
    rows = []
    for n in range(1, requests + 1):
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=deployment, messages=PROMPT, max_completion_tokens=max_completion_tokens)
            completion = raw.parse()
            usage = completion.usage.model_dump() if completion.usage else {}
            headers = dict(raw.headers)
            ledger.record(feature, usage, headers)
            gw = gateway_headers(headers)
            rows.append(Row(n, 200, "ok", usage.get("total_tokens"), gw.get(REMAINING), gw.get(CONSUMED)))
        except Exception as exc:  # openai.APIStatusError and friends
            d = classify_exception(exc)
            rows.append(Row(n, getattr(exc, "status_code", 0) or 0, d.kind, retry_after_s=d.retry_after_s))
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aoai_gateway.smoke", description=__doc__.split("\n")[0])
    p.add_argument("--gateway", default=os.environ.get("APIM_GATEWAY_URL"), help="https://<apim>.azure-api.net")
    p.add_argument("--deployment", default="chat")
    p.add_argument("--requests", type=int, default=12)
    p.add_argument("--max-retries", type=int, default=0)
    args = p.parse_args(argv)
    key = os.environ.get("APIM_SUBSCRIPTION_KEY")
    if not args.gateway or not key:
        print("Set --gateway (or APIM_GATEWAY_URL) and APIM_SUBSCRIPTION_KEY.", file=sys.stderr)
        return 2
    client = make_gateway_client(args.gateway, key, max_retries=args.max_retries)
    ledger = Ledger()
    rows = run_burst(client, args.deployment, args.requests, ledger)
    for row in rows:
        print(row)
    ok = sum(r.status == 200 for r in rows)
    print(f"\n{ok}/{len(rows)} succeeded")
    print(ledger.to_csv(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
