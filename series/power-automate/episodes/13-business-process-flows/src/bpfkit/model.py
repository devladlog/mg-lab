"""Load a process definition (see process/purchase-request-process.json)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Step:
    column: str
    type: str = "text"
    required: bool = False
    valid: list | None = None


@dataclass
class Stage:
    id: str
    name: str
    table: str
    steps: list[Step]
    next: object  # None | "stage id" | {"condition": {...}, "yes": id, "no": id}
    category: str | None = None
    flow_steps: list[str] = field(default_factory=list)
    exit_workflows: list[str] = field(default_factory=list)

    def targets(self) -> list[str]:
        if self.next is None:
            return []
        if isinstance(self.next, str):
            return [self.next]
        return [self.next["yes"], self.next["no"]]


@dataclass
class Process:
    name: str
    unique_name: str
    primary_table: str
    first_stage: str
    stages: dict[str, Stage]
    global_workflows: list[dict]

    @classmethod
    def from_dict(cls, d: dict) -> "Process":
        stages = {}
        for sid, s in d["stages"].items():
            stages[sid] = Stage(
                id=sid, name=s["name"], table=s["table"], category=s.get("category"),
                steps=[Step(x["column"], x.get("type", "text"), x.get("required", False), x.get("valid"))
                       for x in s.get("steps", [])],
                next=s.get("next"), flow_steps=s.get("flowSteps", []),
                exit_workflows=s.get("exitWorkflows", []),
            )
        return cls(d["name"], d["uniqueName"], d["primaryTable"], d["firstStage"], stages,
                   d.get("globalWorkflows", []))

    @classmethod
    def load(cls, path) -> "Process":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def tables(self) -> set[str]:
        return {s.table for s in self.stages.values()}

    def predecessors(self, sid: str) -> list[str]:
        return [s.id for s in self.stages.values() if sid in s.targets()]
