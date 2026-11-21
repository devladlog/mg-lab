from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning" | "info"
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code}: {self.message}"


def has_errors(findings: list[Finding]) -> bool:
    return any(f.level == "error" for f in findings)


def render(findings: list[Finding], ok_text: str) -> str:
    if not findings:
        return ok_text
    return "\n".join(str(f) for f in findings)
