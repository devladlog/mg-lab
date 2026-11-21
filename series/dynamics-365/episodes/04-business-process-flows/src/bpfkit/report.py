"""Where are requests waiting? A stage report straight from the BPF table.

Learn ("Best practices in using business process flow columns") recommends reporting on the business process flow
table itself, not on the deprecated stage columns of the record. Each instance row has the active stage
(activestageid), when that stage started (activestagestartedon) and its state (statecode/statuscode).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from . import path


@dataclass
class Row:
    code: str
    stage: str
    state: str
    started: Optional[date]


@dataclass
class StageLine:
    stage: str
    active: int = 0
    ages: List[int] = field(default_factory=list)
    stuck: List[Row] = field(default_factory=list)

    @property
    def oldest(self) -> int:
        return max(self.ages) if self.ages else 0

    @property
    def average(self) -> float:
        return sum(self.ages) / len(self.ages) if self.ages else 0.0


@dataclass
class Report:
    bpf: str
    total: int
    by_state: Dict[str, int]
    lines: List[StageLine]

    @property
    def stuck(self) -> List[Row]:
        return [r for line in self.lines for r in line.stuck]


def parse_day(value: Optional[str]) -> Optional[date]:
    """activestagestartedon arrives as an ISO date or date-time ('2027-01-04T09:30:00Z')."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date() if "T" in value else date.fromisoformat(value)


def rows_from_api(raw: Iterable[Dict], stage_names: Dict[str, str], lookup_value: str, nav: str,
                  key: str) -> List[Row]:
    rows = []
    for r in raw:
        rec = r.get(nav) or {}
        code = rec.get(key) or path.norm(r.get(lookup_value)) or "?"
        sid = path.norm(r.get("_activestageid_value"))
        rows.append(Row(code=code, stage=stage_names.get(sid, sid or "?"),
                        state=path.state_name(r.get("statecode"), r.get("statuscode")),
                        started=parse_day(r.get("activestagestartedon"))))
    return rows


def build(bpf: str, rows: List[Row], stage_order: List[str], stuck_days: Dict[str, int], today: date) -> Report:
    by_state: Dict[str, int] = {}
    for r in rows:
        by_state[r.state] = by_state.get(r.state, 0) + 1
    lines = {s: StageLine(s) for s in stage_order}
    for r in rows:
        if r.state != "Active":
            continue
        line = lines.setdefault(r.stage, StageLine(r.stage))
        line.active += 1
        if r.started is None:
            continue
        age = (today - r.started).days
        line.ages.append(age)
        if age > stuck_days.get(r.stage, stuck_days.get("default", 5)):
            line.stuck.append(r)
    for line in lines.values():
        line.stuck.sort(key=lambda r: r.started or today)
    return Report(bpf, len(rows), by_state, list(lines.values()))


def render(rep: Report, stuck_days: Dict[str, int], today: date) -> List[str]:
    states = ", ".join(f"{n} {s.lower()}" for s, n in sorted(rep.by_state.items(), key=lambda kv: kv[0]))
    out = [f"{rep.bpf}: {rep.total} instances ({states})", "",
           f"{'stage':<16}{'active':>7}{'oldest':>8}{'avg':>7}  stuck"]
    for line in rep.lines:
        limit = stuck_days.get(line.stage, stuck_days.get("default", 5))
        stuck = f"{len(line.stuck)} over {limit} d" if line.stuck else ""
        out.append(f"{line.stage:<16}{line.active:>7}{line.oldest:>7}d{line.average:>7.1f}  {stuck}".rstrip())
    if rep.stuck:
        out.append("")
        for r in rep.stuck:
            out.append(f"  {r.code:<10} {r.stage:<16} since {r.started.isoformat()} ({(today - r.started).days} d)")
    return out
