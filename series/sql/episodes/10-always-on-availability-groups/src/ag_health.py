"""Availability group failover readiness: turn the rows of sql/a07-health.sql into a verdict per replica.

What decides whether a failover loses data (Learn: availability modes, planned manual failover, automatic failover):

* a planned manual failover needs SYNCHRONOUS_COMMIT and a synchronized secondary;
* automatic failover also needs FAILOVER_MODE = AUTOMATIC;
* an asynchronous-commit secondary can only be forced, and a forced failover can lose data.

A replica must also be connected and its database not suspended. The verdicts, for each SECONDARY:

    AUTOMATIC FAILOVER READY   synchronous commit, automatic, SYNCHRONIZED, HEALTHY, connected, not suspended
    MANUAL FAILOVER READY      the same, but FAILOVER_MODE is MANUAL
    DATA LOSS POSSIBLE         asynchronous commit, or not (yet) synchronized
    NOT READY                  disconnected, suspended, or no database row

The PRIMARY row is reported as PRIMARY. ``summary`` says in one line whether the group can fail over without data loss.

    python src/ag_lab.py --engine sqlserver --health        # runs the query on the primary and prints this
"""
from __future__ import annotations

from dataclasses import dataclass

AUTO, MANUAL, LOSS, NOT_READY, PRIMARY = ("AUTOMATIC FAILOVER READY", "MANUAL FAILOVER READY", "DATA LOSS POSSIBLE",
                                          "NOT READY", "PRIMARY")
COLUMNS = ["Replica", "Role", "AvailabilityMode", "FailoverMode", "ConnectedState", "SyncState", "SyncHealth",
           "IsSuspended", "LogSendQueueKB", "RedoQueueKB"]


@dataclass(frozen=True)
class Replica:
    name: str
    role: str | None
    availability_mode: str | None
    failover_mode: str | None
    connected: str | None
    sync_state: str | None
    sync_health: str | None
    suspended: bool
    log_send_queue_kb: int | None
    redo_queue_kb: int | None

    @classmethod
    def from_row(cls, row) -> "Replica":
        name, role, mode, fmode, conn, state, health, susp, send, redo = row
        return cls(str(name), role, mode, fmode, conn, state, health, susp in (1, True, "1"),
                   None if send is None else int(send), None if redo is None else int(redo))


@dataclass(frozen=True)
class Verdict:
    replica: str
    verdict: str
    reason: str


def assess_one(r: Replica) -> Verdict:
    if r.role == "PRIMARY":
        return Verdict(r.name, PRIMARY, "accepts writes")
    if r.connected != "CONNECTED":
        return Verdict(r.name, NOT_READY, f"connection state {r.connected or 'unknown'}")
    if r.sync_state is None:
        return Verdict(r.name, NOT_READY, "no database row yet (seeding has not started, or the database was not added)")
    if r.suspended:
        return Verdict(r.name, NOT_READY, "data movement is suspended")
    if r.availability_mode != "SYNCHRONOUS_COMMIT":
        return Verdict(r.name, LOSS, "asynchronous commit: a failover can only be forced and can lose data")
    if r.sync_state != "SYNCHRONIZED":
        return Verdict(r.name, LOSS, f"{r.sync_state}: not synchronized yet, a failover now could lose data")
    if r.sync_health != "HEALTHY":
        return Verdict(r.name, NOT_READY, f"synchronization health {r.sync_health}")
    if r.failover_mode == "AUTOMATIC":
        return Verdict(r.name, AUTO, "synchronous commit, synchronized, healthy: no data loss")
    return Verdict(r.name, MANUAL, "synchronous commit, synchronized, healthy: a planned failover loses no data")


def assess(rows) -> list[Verdict]:
    return [assess_one(r if isinstance(r, Replica) else Replica.from_row(r)) for r in rows]


def summary(verdicts: list[Verdict]) -> str:
    if not any(v.verdict == PRIMARY for v in verdicts):
        return "NO PRIMARY: the group is not online on this replica, or is resolving"
    secondaries = [v for v in verdicts if v.verdict != PRIMARY]
    if not secondaries:
        return "NO SECONDARY: nothing to fail over to"
    if any(v.verdict == AUTO for v in secondaries):
        return "FAILOVER READY, NO DATA LOSS (automatic)"
    if any(v.verdict == MANUAL for v in secondaries):
        return "FAILOVER READY, NO DATA LOSS (manual)"
    return "NOT SAFE TO FAIL OVER: " + "; ".join(f"{v.replica} {v.verdict}" for v in secondaries)


def render(verdicts: list[Verdict]) -> str:
    if not verdicts:
        return "(no replicas)"
    w = max(len(v.replica) for v in verdicts)
    x = max(len(v.verdict) for v in verdicts)
    lines = [f"{v.replica.ljust(w)}  {v.verdict.ljust(x)}  {v.reason}" for v in verdicts]
    return "\n".join(lines + [summary(verdicts)])
