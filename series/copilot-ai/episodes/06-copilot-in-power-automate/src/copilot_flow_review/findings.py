from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" | "warning" | "info"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.severity:<7} {self.where}: {self.message}"


def worst(findings: list[Finding]) -> str:
    for level in ("error", "warning", "info"):
        if any(f.severity == level for f in findings):
            return level
    return "ok"
