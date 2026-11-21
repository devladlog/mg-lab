"""A process instance: active stage, traversed path, stage gating, branching, abort/finish.

Behaviour implemented from Microsoft Learn:
  * required steps gate the move to the next stage; a required Two Options step must be Yes (overview)
  * the branch is chosen from the values of the steps in the stage before the condition (branching tutorial)
  * through code you may only move to the next or the previous stage; forward moves go one stage at a time
  * Finished is only possible at the last stage; Abort at any stage (statecode/statuscode, code article)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Process, Stage

OPERATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "contains": lambda a, b: a is not None and b in a,
}


class BpfError(Exception):
    pass


class GateError(BpfError):
    """Required steps are empty: the user sees the stage's required fields and can't move on."""

    def __init__(self, stage: str, missing: list[str]):
        super().__init__(f"stage '{stage}' has required steps without a value: {', '.join(missing)}")
        self.stage, self.missing = stage, missing


def is_empty(value, step_type: str) -> bool:
    if step_type == "twoOptions":
        return value is not True  # No counts as empty for a required Two Options step
    return value is None or (isinstance(value, str) and value.strip() == "")


def evaluate(condition: dict, record: dict) -> bool:
    results = [OPERATORS[r["operator"]](record.get(r["column"]), r["value"]) for r in condition["rules"]]
    return all(results) if condition["op"] == "and" else any(results)


def next_stage_id(stage: Stage, record: dict) -> str | None:
    if stage.next is None:
        return None
    if isinstance(stage.next, str):
        return stage.next
    return stage.next["yes"] if evaluate(stage.next["condition"], record) else stage.next["no"]


def missing_required(stage: Stage, record: dict) -> list[str]:
    return [s.column for s in stage.steps if s.required and is_empty(record.get(s.column), s.type)]


@dataclass
class Instance:
    process: Process
    record: dict
    active: str = ""
    traversed: list[str] = field(default_factory=list)
    state: str = "Active"  # Active | Finished | Aborted
    log: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.active:
            self.active = self.process.first_stage
            self.traversed = [self.active]

    @property
    def stage(self) -> Stage:
        return self.process.stages[self.active]

    def _need_active(self):
        if self.state != "Active":
            raise BpfError(f"the process instance is {self.state}")

    def update(self, **values) -> None:
        self.record.update(values)

    def next(self) -> str:
        self._need_active()
        if self.stage.next is None:
            raise BpfError("last stage: finish the process instead of moving to the next stage")
        missing = missing_required(self.stage, self.record)
        if missing:
            raise GateError(self.stage.name, missing)
        target = next_stage_id(self.stage, self.record)
        self.active = target
        self.traversed.append(target)
        self.log.append(f"next -> {self.stage.name}")
        return target

    def previous(self) -> str:
        self._need_active()
        if len(self.traversed) < 2:
            raise BpfError("already at the first stage")
        self.traversed.pop()
        self.active = self.traversed[-1]
        self.log.append(f"previous -> {self.stage.name}")
        return self.active

    def set_active(self, stage_id: str) -> str:
        """Code can only move one stage forward (the next on the active path) or one back."""
        self._need_active()
        if len(self.traversed) > 1 and stage_id == self.traversed[-2]:
            return self.previous()
        if stage_id == next_stage_id(self.stage, self.record):
            return self.next()
        raise BpfError(f"can only move to the next or previous stage, not to '{stage_id}'")

    def finish(self) -> None:
        self._need_active()
        if self.stage.next is not None:
            raise BpfError("Finished is only possible at the last stage")
        missing = missing_required(self.stage, self.record)
        if missing:
            raise GateError(self.stage.name, missing)
        self.state = "Finished"
        self.log.append("finished")

    def abort(self) -> None:
        self._need_active()
        self.state = "Aborted"
        self.log.append("aborted")

    def reactivate(self) -> None:
        if self.state != "Aborted":
            raise BpfError("only an aborted instance can be reactivated")
        self.state = "Active"
        self.log.append("reactivated")

    def active_path(self) -> list[str]:
        """The stages the record would visit with its current values (the designer's active path)."""
        path, sid, seen = [], self.process.first_stage, set()
        while sid and sid not in seen:
            path.append(sid)
            seen.add(sid)
            sid = next_stage_id(self.process.stages[sid], self.record)
        return path
