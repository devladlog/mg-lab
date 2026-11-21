"""The AI system register: a YAML file in the repo, validated like code."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

TIERS = ("low", "medium", "high")
RESIDENCY = ("eu", "any")
REQUIRED = ("id", "name", "owner", "purpose", "tier", "approved_models", "next_review")


class RegisterError(ValueError):
    """The register file is invalid; the message lists every problem found."""


@dataclass
class System:
    id: str
    name: str
    owner: str
    purpose: str
    tier: str
    approved_models: list[tuple[str, str]]
    next_review: date
    uses_retrieval: bool = False
    personal_data: bool = False
    data_residency: str = "any"
    human_oversight: str = ""
    rai_gate: dict = field(default_factory=dict)


def _as_date(value, where: str, problems: list[str]) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        problems.append(f"{where}: '{value}' is not a YYYY-MM-DD date")
        return None


def parse(data: dict) -> dict[str, System]:
    """Validate the whole file and collect every problem before failing, so one review fixes them all."""
    problems: list[str] = []
    systems: dict[str, System] = {}
    entries = (data or {}).get("systems")
    if not isinstance(entries, list) or not entries:
        raise RegisterError("register: 'systems' must be a non-empty list")
    for i, e in enumerate(entries):
        where = f"systems[{i}]" + (f" ({e.get('id')})" if isinstance(e, dict) and e.get("id") else "")
        if not isinstance(e, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        missing = [k for k in REQUIRED if e.get(k) in (None, "", [])]
        if missing:
            problems.append(f"{where}: missing {', '.join(missing)}")
            continue
        if e["id"] in systems:
            problems.append(f"{where}: duplicate id '{e['id']}'")
        if e["tier"] not in TIERS:
            problems.append(f"{where}: tier must be one of {TIERS}")
        residency = e.get("data_residency", "any")
        if residency not in RESIDENCY:
            problems.append(f"{where}: data_residency must be one of {RESIDENCY}")
        models = []
        for m in e["approved_models"]:
            if not isinstance(m, dict) or not m.get("name") or not m.get("version"):
                problems.append(f"{where}: approved_models entries need name and version (pin the version)")
            else:
                models.append((str(m["name"]), str(m["version"])))
        review = _as_date(e["next_review"], f"{where}.next_review", problems)
        gate = dict(e.get("rai_gate") or {})
        if gate:
            gate["date"] = _as_date(gate.get("date"), f"{where}.rai_gate.date", problems)
            if gate.get("verdict") not in ("PASS", "FAIL"):
                problems.append(f"{where}: rai_gate.verdict must be PASS or FAIL")
        if e["tier"] == "high" and not str(e.get("human_oversight") or "").strip():
            problems.append(f"{where}: tier high requires a human_oversight description")
        systems[e["id"]] = System(
            id=e["id"], name=e["name"], owner=e["owner"], purpose=e["purpose"], tier=e["tier"],
            approved_models=models, next_review=review or date.min,
            uses_retrieval=bool(e.get("uses_retrieval")), personal_data=bool(e.get("personal_data")),
            data_residency=residency, human_oversight=str(e.get("human_oversight") or "").strip(), rai_gate=gate,
        )
    if problems:
        raise RegisterError("register is invalid:\n  - " + "\n  - ".join(problems))
    return systems


def load(path: str | Path) -> dict[str, System]:
    return parse(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
