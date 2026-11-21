"""Business rules of the VMO renewal register (Contoso Vendor Renewals and Offboarding policy, episode 3)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DECIDE_DAYS_BEFORE = 90      # budget owner decides at least 90 days before renewal
ESCALATE_DAYS_BEFORE = 60    # VMO escalates to the owner's manager 60 days before renewal
DECIDE_SOON_DAYS = 45        # status "decide-soon" when this close to decideBy
MAX_NOTE_LENGTH = 200

DATA_FILE = Path(__file__).parent / "data" / "vendors.json"


class RegisterError(Exception):
    """A request the register refuses. `code` is machine readable, `status` the HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class Register:
    vendors: list[dict]
    reminders: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = DATA_FILE) -> "Register":
        return cls(vendors=json.loads(Path(path).read_text(encoding="utf-8")))

    # ---- reads -----------------------------------------------------------------------------
    def _view(self, vendor: dict, today: date) -> dict:
        renewal = date.fromisoformat(vendor["renewalDate"])
        decide_by = renewal - timedelta(days=DECIDE_DAYS_BEFORE)
        escalate_on = renewal - timedelta(days=ESCALATE_DAYS_BEFORE)
        days = (decide_by - today).days
        if today >= escalate_on:
            status = "escalated"
        elif days < 0:
            status = "overdue"
        elif days <= DECIDE_SOON_DAYS:
            status = "decide-soon"
        else:
            status = "open"
        return {**vendor, "decideBy": decide_by.isoformat(), "escalateOn": escalate_on.isoformat(),
                "daysToDecision": days, "status": status}

    def list_renewals(self, today: date, within_days: int | None = None, owner: str | None = None) -> list[dict]:
        if within_days is not None and not 1 <= within_days <= 730:
            raise RegisterError(400, "invalid_request", "withinDays must be a whole number from 1 to 730.")
        rows = [self._view(v, today) for v in self.vendors]
        if within_days is not None:
            limit = today + timedelta(days=within_days)
            rows = [r for r in rows if date.fromisoformat(r["renewalDate"]) <= limit]
        if owner:
            rows = [r for r in rows if r["owner"].lower() == owner.strip().lower()]
        return sorted(rows, key=lambda r: r["renewalDate"])

    def get_vendor(self, vendor_id: str, today: date) -> dict:
        for v in self.vendors:
            if v["vendorId"] == vendor_id:
                return self._view(v, today)
        raise RegisterError(404, "not_found", "No vendor with that id.")

    # ---- writes ----------------------------------------------------------------------------
    def create_reminder(self, vendor_id: str, body: object, today: date) -> dict:
        vendor = self.get_vendor(vendor_id, today)
        if not isinstance(body, dict):
            raise RegisterError(400, "invalid_request", "The body must be a JSON object.")
        try:
            remind_on = date.fromisoformat(str(body.get("remindOn", "")))
        except ValueError:
            raise RegisterError(400, "invalid_request", "remindOn must be a date in YYYY-MM-DD format.") from None
        decide_by = date.fromisoformat(vendor["decideBy"])
        if not today <= remind_on <= decide_by:
            raise RegisterError(400, "invalid_request",
                                f"remindOn must be a date from {today.isoformat()} to the decide-by date {decide_by.isoformat()}.")
        note = body.get("note", "")
        if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH:
            raise RegisterError(400, "invalid_request", f"note must be text of at most {MAX_NOTE_LENGTH} characters.")
        reminder = {"reminderId": f"rem-{len(self.reminders) + 1:04d}", "vendorId": vendor_id,
                    "remindOn": remind_on.isoformat(), "note": note}
        self.reminders.append(reminder)
        return reminder
