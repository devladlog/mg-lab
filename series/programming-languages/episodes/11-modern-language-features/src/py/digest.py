"""Contoso request digest, Python 3.13 edition.

Same input and same output as the TypeScript, C# and PowerShell versions
(see ../../expected/digest.txt). Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import batched
from pathlib import Path
from typing import ReadOnly, TypedDict
from warnings import deprecated

HIGH_PRIORITY_CENTS = 5_000_000  # 50,000.00 EUR
BOARD_CENTS = 25_000_000  # 250,000.00 EUR
BATCH_SIZE = 4


class RawRequest(TypedDict):
    """Shape of one JSON element. ReadOnly (3.13) says: do not assign to these keys."""

    code: ReadOnly[str]
    title: ReadOnly[str]
    department: ReadOnly[str]
    budget: ReadOnly[Decimal]
    requestedBy: ReadOnly[str]


class Route(StrEnum):
    TEAM_LEAD = "TeamLead"
    FINANCE = "Finance"
    BOARD = "Board"


@dataclass(frozen=True, slots=True)
class Request:
    code: str
    title: str
    department: str
    cents: int

    @property
    def route(self) -> Route:
        return route_for(self.cents)

    @property
    def high_priority(self) -> bool:
        return self.cents >= HIGH_PRIORITY_CENTS


@dataclass(frozen=True, slots=True)
class Accepted:
    request: Request


@dataclass(frozen=True, slots=True)
class Rejected:
    code: str
    reason: str


type Outcome = Accepted | Rejected  # PEP 695 type alias (3.12)


@dataclass(frozen=True, slots=True)
class DepartmentTotal:
    department: str
    count: int
    cents: int


@dataclass(frozen=True, slots=True)
class Digest:
    accepted: tuple[Request, ...]
    rejected: tuple[Rejected, ...]
    total_cents: int
    high_priority: int
    routes: dict[Route, int]
    departments: tuple[DepartmentTotal, ...]
    largest: tuple[Request, ...]
    batches: tuple[tuple[str, ...], ...]


def route_for(cents: int) -> Route:
    if cents >= BOARD_CENTS:
        return Route.BOARD
    if cents >= HIGH_PRIORITY_CENTS:
        return Route.FINANCE
    return Route.TEAM_LEAD


def to_cents(budget: Decimal) -> int:
    return int(budget * 100)


@deprecated("floats cannot hold 49999.99 exactly; parse JSON with parse_float=Decimal")
def to_cents_float(budget: float) -> int:
    return int(budget * 100)  # the classic bug, kept so the demo can show it


def validate(raw: RawRequest) -> Outcome:
    if raw["budget"] <= 0:
        return Rejected(raw["code"], "budget must be greater than zero")
    return Accepted(
        Request(
            code=raw["code"],
            title=raw["title"],
            department=raw["department"].strip().upper(),
            cents=to_cents(raw["budget"]),
        )
    )


def count_by[T, K](items: Iterable[T], key: Callable[[T], K]) -> dict[K, int]:
    """PEP 695 generic function: no TypeVar boilerplate."""
    counts: dict[K, int] = {}
    for item in items:
        k = key(item)
        counts[k] = counts.get(k, 0) + 1
    return counts


def build_digest(raws: Sequence[RawRequest]) -> Digest:
    outcomes = [validate(raw) for raw in raws]
    accepted: list[Request] = []
    rejected: list[Rejected] = []
    for outcome in outcomes:
        match outcome:
            case Accepted(request):
                accepted.append(request)
            case Rejected():
                rejected.append(outcome)

    by_route = count_by(accepted, lambda r: r.route)
    routes = {route: by_route.get(route, 0) for route in Route}

    totals: dict[str, tuple[int, int]] = {}
    for r in accepted:
        count, cents = totals.get(r.department, (0, 0))
        totals[r.department] = (count + 1, cents + r.cents)
    departments = tuple(
        DepartmentTotal(name, count, cents)
        for name, (count, cents) in sorted(totals.items(), key=lambda kv: (-kv[1][1], kv[0]))
    )

    largest = tuple(sorted(accepted, key=lambda r: (-r.cents, r.code))[:3])
    batches = tuple(tuple(r.code for r in chunk) for chunk in batched(accepted, BATCH_SIZE, strict=False))

    return Digest(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        total_cents=sum(r.cents for r in accepted),
        high_priority=sum(1 for r in accepted if r.high_priority),
        routes=routes,
        departments=departments,
        largest=largest,
        batches=batches,
    )


def money(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def render(digest: Digest) -> str:
    lines = [
        "Contoso request digest",
        f"accepted {len(digest.accepted)}, rejected {len(digest.rejected)}, "
        f"total {money(digest.total_cents)} EUR, high priority {digest.high_priority}",
        "rejected:",
        *(f"  {r.code}  {r.reason}" for r in digest.rejected),
        "by route:",
        *(f"  {route.value:<9}{count:>2}" for route, count in digest.routes.items()),
        "by department:",
        *(f"  {d.department:<6}{d.count:>2}  {money(d.cents):>13} EUR" for d in digest.departments),
        "largest three:",
        *(f"  {i}. {r.code}  {r.title}  {money(r.cents)} EUR" for i, r in enumerate(digest.largest, 1)),
        f"review batches of {BATCH_SIZE}:",
        *(f"  {i}: {', '.join(codes)}" for i, codes in enumerate(digest.batches, 1)),
    ]
    return "\n".join(lines) + "\n"


def load(path: Path) -> list[RawRequest]:
    # parse_float=Decimal keeps 49999.99 exact; json gives int for 12000, so convert both.
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal, parse_int=Decimal)
    return [
        RawRequest(
            code=item["code"],
            title=item["title"],
            department=item["department"],
            budget=item["budget"],
            requestedBy=item["requestedBy"],
        )
        for item in data
    ]


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("usage: python digest.py <requests.json>", file=sys.stderr)
        return 2
    sys.stdout.write(render(build_digest(load(Path(argv[0])))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
