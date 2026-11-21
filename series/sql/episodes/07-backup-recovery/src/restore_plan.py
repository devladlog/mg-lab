"""Restore planner: from the rows of msdb.dbo.backupset (+ backupmediafamily) to the RESTORE statements that bring a
database to a point in time. Pure Python, no connection: the runner feeds it the rows of sql/msdb-history.sql.

The rules (all from Learn, "Restore a SQL Server database to a point in time (full recovery model)" and
"Differential backups"):
* start from the most recent full backup that ended before the target, copy-only backups never count
  (they are not a differential base);
* then the most recent differential taken after that full (and before the next full), ended before the target;
* then every log backup after that, in order, up to and including the first one that reaches the target time;
* every statement is WITH NORECOVERY and carries the same STOPAT; the last one is a separate RESTORE ... WITH RECOVERY;
* if the target is after the last log backup, Learn says the database is left unrecovered: reported as a warning.
Gaps are detected with the LSNs: a log backup whose first_lsn is greater than the previous backup's last_lsn
means log records are missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


class PlanError(Exception):
    """No valid restore sequence exists for the target time."""


@dataclass(frozen=True)
class BackupRow:
    kind: str                    # msdb backupset.type: 'D' full, 'I' differential, 'L' log
    start: datetime
    finish: datetime
    first_lsn: Decimal
    last_lsn: Decimal
    copy_only: bool
    device: str                  # backupmediafamily.physical_device_name

    @property
    def label(self) -> str:
        return {"D": "full", "I": "differential", "L": "log"}.get(self.kind, self.kind)


@dataclass
class Plan:
    steps: list[BackupRow]
    target: datetime
    warnings: list[str] = field(default_factory=list)

    @property
    def files(self) -> list[str]:
        return [s.device for s in self.steps]


def build_plan(rows: list[BackupRow], target: datetime) -> Plan:
    rows = sorted(rows, key=lambda r: (r.start, r.first_lsn))
    fulls = [r for r in rows if r.kind == "D" and not r.copy_only]
    candidates = [r for r in fulls if r.finish <= target]
    if not candidates:
        raise PlanError(f"no full backup finished before {target:%Y-%m-%d %H:%M:%S}")
    full = max(candidates, key=lambda r: r.finish)
    later_fulls = [r for r in fulls if r.start > full.start]
    boundary = min((r.start for r in later_fulls), default=None)

    diffs = [r for r in rows if r.kind == "I" and r.start >= full.finish and r.finish <= target
             and (boundary is None or r.start < boundary)]
    base = max(diffs, key=lambda r: r.finish) if diffs else full
    steps = [full] + ([base] if base is not full else [])

    plan = Plan(steps, target)
    logs = sorted((r for r in rows if r.kind == "L" and r.last_lsn > base.last_lsn), key=lambda r: r.first_lsn)
    previous = base
    reached = False
    for log in logs:
        if log.first_lsn > previous.last_lsn:
            raise PlanError(f"log chain broken: {log.device} starts at LSN {log.first_lsn}, "
                            f"the previous backup ends at {previous.last_lsn}")
        plan.steps.append(log)
        previous = log
        if log.finish >= target:
            reached = True
            break
    if not reached:
        plan.warnings.append("the target time is after the last log backup: the copy would stay in the RESTORING "
                             "state (Learn: STOPAT after the last log backup leaves the database unrecovered)")
    return plan


def _literal(text: str) -> str:
    return "N'" + text.replace("'", "''") + "'"


def render(plan: Plan, database: str, moves: dict[str, str]) -> list[str]:
    """RESTORE statements for the plan. `moves` maps each logical file name to its new path (MOVE takes literals)."""
    stop = f"'{plan.target:%Y-%m-%dT%H:%M:%S.%f}'"[:-4] + "'"          # ISO 8601 with milliseconds
    statements = []
    for i, step in enumerate(plan.steps):
        verb = "RESTORE LOG" if step.kind == "L" else "RESTORE DATABASE"
        options = []
        if i == 0:
            options += [f"MOVE {_literal(name)} TO {_literal(path)}" for name, path in moves.items()]
        options += ["NORECOVERY", "CHECKSUM", f"STOPAT = {stop}"]
        statements.append(f"{verb} {database} FROM DISK = {_literal(step.device)} WITH {', '.join(options)};")
    statements.append(f"RESTORE DATABASE {database} WITH RECOVERY;")
    return statements
