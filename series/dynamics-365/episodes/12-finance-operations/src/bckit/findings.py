"""A finding is one line of a report: level (error | warning | info), a stable rule id, a subject and a message."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class Finding:
    level: str
    rule: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.rule}  {self.subject}: {self.message}"


def tally(findings: Iterable[Finding]) -> str:
    fs: List[Finding] = list(findings)
    return (f"{sum(f.level == 'error' for f in fs)} error(s), {sum(f.level == 'warning' for f in fs)} warning(s), "
            f"{sum(f.level == 'info' for f in fs)} info")


def exit_code(findings: Iterable[Finding]) -> int:
    """1 when there is at least one error, so a scheduled run can fail on it."""
    return 1 if any(f.level == "error" for f in findings) else 0
