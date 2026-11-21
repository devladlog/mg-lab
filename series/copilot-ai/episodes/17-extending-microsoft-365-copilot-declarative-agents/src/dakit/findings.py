from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    level: str      # "error" | "warning"
    where: str      # file or json path
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]
