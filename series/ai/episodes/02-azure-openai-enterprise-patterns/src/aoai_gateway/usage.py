"""Per-feature token ledger built from the response `usage` and the gateway's headers."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

REMAINING = "x-gateway-remaining-tokens"
REMAINING_QUOTA = "x-gateway-remaining-quota-tokens"
CONSUMED = "x-gateway-tokens-consumed"


def gateway_headers(headers: Mapping[str, str]) -> dict[str, int]:
    """Pick the llm-token-limit headers configured in the policy (names are ours, see aoai-api.xml)."""
    out = {}
    lower = {k.lower(): v for k, v in headers.items()}
    for name in (REMAINING, REMAINING_QUOTA, CONSUMED):
        try:
            out[name] = int(lower[name])
        except (KeyError, ValueError):
            pass
    return out


@dataclass
class Ledger:
    totals: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    last_remaining: int | None = None

    def record(self, feature: str, usage: Mapping[str, int] | None, headers: Mapping[str, str] | None = None) -> None:
        t = self.totals[feature]
        t["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            t[k] += int((usage or {}).get(k, 0) or 0)
        gw = gateway_headers(headers or {})
        if REMAINING in gw:
            self.last_remaining = gw[REMAINING]

    def low_budget(self, threshold: int) -> bool:
        """True when the gateway says fewer than `threshold` tokens are left this minute: slow down before a 429."""
        return self.last_remaining is not None and self.last_remaining < threshold

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["feature", "calls", "prompt_tokens", "completion_tokens", "total_tokens"])
        for feature in sorted(self.totals):
            t = self.totals[feature]
            w.writerow([feature, t["calls"], t["prompt_tokens"], t["completion_tokens"], t["total_tokens"]])
        return buf.getvalue()
