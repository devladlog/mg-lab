"""RPO exposure report: turn the rows of sql/h01-rpo-exposure.sql into a verdict per database.

RPO (recovery point objective) is how much data you can afford to lose, as time. With backups the data you would lose
is everything since the newest backup that could be restored, so ``MinutesAtRisk`` (computed in SQL from msdb) is
compared with the target. The rules:

* a database that is not ONLINE (RESTORING: the old primary after a failover, an unrecovered copy) or that is a
  read-only log-shipping standby is SKIPPED: it is not where backups are taken from;
* no full backup in msdb is NO BACKUP, whatever else exists (a log backup alone cannot be restored);
* MinutesAtRisk above the target is AT RISK; otherwise OK;
* SIMPLE recovery has no log backups, so the exposure is the time since the last full/differential and a restore
  can only go to the end of a backup (the reason says so); a FULL database with no log backup yet says that too.

    python src/ha_lab.py --engine sqlserver --report --rpo 15      # runs the query on CON-SQL01 and prints this
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

OK, AT_RISK, NO_BACKUP, SKIPPED = "OK", "AT RISK", "NO BACKUP", "SKIPPED"
COLUMNS = ["DatabaseName", "RecoveryModel", "State", "IsStandby", "LastFull", "LastDiff", "LastLog", "MinutesAtRisk"]


@dataclass(frozen=True)
class Exposure:
    name: str
    recovery_model: str
    state: str
    is_standby: bool
    last_full: datetime | None
    last_diff: datetime | None
    last_log: datetime | None
    minutes_at_risk: int | None

    @classmethod
    def from_row(cls, row) -> "Exposure":
        name, model, state, standby, full, diff, log, minutes = row
        return cls(str(name), str(model), str(state), bool(standby), full, diff, log,
                   None if minutes is None else int(minutes))


@dataclass(frozen=True)
class Verdict:
    name: str
    verdict: str
    reason: str


def assess_one(e: Exposure, rpo_minutes: int) -> Verdict:
    if e.state != "ONLINE":
        return Verdict(e.name, SKIPPED, f"{e.state}: backups are taken from the database that is ONLINE")
    if e.is_standby:
        return Verdict(e.name, SKIPPED, "read-only standby copy: back up the primary")
    if e.last_full is None or e.minutes_at_risk is None:
        extra = " (log backups without a full backup cannot be restored)" if e.last_log is not None else ""
        return Verdict(e.name, NO_BACKUP, "no full backup in msdb history" + extra)
    notes = []
    if e.recovery_model == "SIMPLE":
        notes.append("SIMPLE recovery: no log backups, a restore can only reach the end of a full or differential backup")
    elif e.last_log is None:
        notes.append(f"{e.recovery_model} recovery but no log backup yet: the log keeps growing")
    if e.minutes_at_risk > rpo_minutes:
        return Verdict(e.name, AT_RISK, "; ".join([f"{e.minutes_at_risk} min since the newest backup, target {rpo_minutes}"] + notes))
    return Verdict(e.name, OK, "; ".join([f"{e.minutes_at_risk} min since the newest backup, target {rpo_minutes}"] + notes))


def assess(rows, rpo_minutes: int) -> list[Verdict]:
    """rows: tuples in the order of COLUMNS (or Exposure objects)."""
    if rpo_minutes < 0:
        raise ValueError("the RPO target cannot be negative")
    exposures = [r if isinstance(r, Exposure) else Exposure.from_row(r) for r in rows]
    return [assess_one(e, rpo_minutes) for e in exposures]


def render(verdicts: list[Verdict]) -> str:
    if not verdicts:
        return "(no user databases)"
    w = max(len(v.name) for v in verdicts)
    return "\n".join(f"{v.name.ljust(w)}  {v.verdict.ljust(9)}  {v.reason}" for v in verdicts)
