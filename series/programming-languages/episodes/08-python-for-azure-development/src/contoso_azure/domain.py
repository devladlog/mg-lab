"""Pure business rules: no Azure, no I/O. Same rules as episodes 5 to 7."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

HIGH_FROM = Decimal("50000")
BOARD_FROM = Decimal("250000")
_CODE = re.compile(r"PR-\d{4}-\d{4}")


@dataclass(frozen=True, slots=True)
class Request:
    code: str
    title: str
    department: str
    budget: Decimal
    submitted: date

    @property
    def priority(self) -> str:
        return priority_for(self.budget)


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int  # 1 = the header, like the PowerShell episode
    error_id: str
    message: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    valid: tuple[Request, ...]
    rejected: tuple[Rejection, ...]


@dataclass(frozen=True, slots=True)
class Approver:
    role: str
    name: str


@dataclass(frozen=True, slots=True)
class Route:
    request: Request
    department: str  # the spelling from the approvers file: "it" becomes "IT"
    approvers: tuple[Approver, ...]


def priority_for(budget: Decimal) -> str:
    """>= 50,000 is High and >= 250,000 is Board: the series rule from episode 6."""
    if budget >= BOARD_FROM:
        return "Board"
    if budget >= HIGH_FROM:
        return "High"
    return "Normal"


def parse_requests(text: str) -> ParseResult:
    """Parse the CSV text. A bad row is reported and skipped; the other rows are still processed."""
    valid: list[Request] = []
    rejected: list[Rejection] = []
    for row, record in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            valid.append(_to_request(record))
        except ValueError as problem:
            error_id, _, message = str(problem).partition("|")
            rejected.append(Rejection(row, error_id, message))
    return ParseResult(tuple(valid), tuple(rejected))


def _to_request(record: dict[str, str | None]) -> Request:
    def field(name: str) -> str:
        return (record.get(name) or "").strip()

    code = field("code")
    if not _CODE.fullmatch(code):
        raise ValueError(f"invalid_code|Code '{code}' does not look like PR-2026-0042.")
    if not field("title"):
        raise ValueError(f"missing_title|{code} has no title.")
    if not field("department"):
        raise ValueError(f"missing_department|{code} has no department.")
    try:
        budget = Decimal(field("budget").replace(",", ""))
    except InvalidOperation:
        budget = Decimal(0)
    if not budget.is_finite() or budget <= 0:
        raise ValueError(f"invalid_budget|{code} budget '{field('budget')}' is not a positive number.")
    try:
        submitted = datetime.strptime(field("submitted"), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"invalid_date|{code} submitted '{field('submitted')}' is not a yyyy-MM-dd date.") from None
    return Request(code, field("title"), field("department"), budget, submitted)


def load_approvers(text: str) -> dict[str, Any]:
    return json.loads(text)  # type: ignore[no-any-return]


def route_for(request: Request, directory: dict[str, Any]) -> Route | None:
    """Manager, then finance (High, Board), then the board (Board). None when the department is unknown."""
    departments: dict[str, dict[str, str]] = directory["departments"]
    match = next((name for name in departments if name.casefold() == request.department.casefold()), None)
    if match is None:
        return None
    entry = departments[match]
    approvers = [Approver("Manager", entry["manager"])]
    if request.priority in ("High", "Board"):
        approvers.append(Approver("Finance", entry["finance"]))
    if request.priority == "Board":
        approvers.append(Approver("Board", directory["board"]))
    return Route(request, match, tuple(approvers))


def pack_document(route: Route) -> dict[str, Any]:
    """The JSON approval pack. The budget is a string: Decimal is not JSON serializable, float would round."""
    request = route.request
    return {
        "request": {
            "code": request.code,
            "title": request.title,
            "department": route.department,
            "budget": str(request.budget),
            "submitted": request.submitted.isoformat(),
        },
        "route": {
            "priority": request.priority,
            "approvers": [{"role": a.role, "name": a.name} for a in route.approvers],
        },
    }
