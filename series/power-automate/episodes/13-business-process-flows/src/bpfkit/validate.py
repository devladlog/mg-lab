"""Design-time rules for a business process flow, each taken from Microsoft Learn.

Limits (business-process-flows-overview, create-business-process-flow, business-process-flows-code):
  * up to 30 stages per process, 30 steps per stage, 5 tables per process, 10 active BPFs per table
Branching (enhance-business-process-flows-branching):
  * a rule must be based on steps of the stage immediately before the condition
  * a rule may combine conditions with AND or OR, not both
  * peer branches must merge into one stage, or all of them must end the process
  * branch depth: the two Learn tutorials disagree (five vs ten levels): we warn at more than five
Other:
  * a required Two Options step only passes when its value is Yes (overview)
  * a workflow on Stage Exit of the last stage never runs: use a global workflow (overview)
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Process

MAX_STAGES = 30
MAX_STEPS = 30
MAX_TABLES = 5
MAX_ACTIVE_PER_TABLE = 10
SAFE_BRANCH_DEPTH = 5  # the stricter of the two numbers on Learn


@dataclass
class Finding:
    level: str  # error | warning
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.where}: {self.message}"


def validate(p: Process) -> list[Finding]:
    out: list[Finding] = []
    err = lambda c, w, m: out.append(Finding("error", c, w, m))
    warn = lambda c, w, m: out.append(Finding("warning", c, w, m))

    if len(p.stages) > MAX_STAGES:
        err("BPF001", p.name, f"{len(p.stages)} stages; the limit is {MAX_STAGES} per process")
    if len(p.tables()) > MAX_TABLES:
        err("BPF003", p.name, f"{len(p.tables())} tables; a process can span at most {MAX_TABLES}")
    if p.first_stage not in p.stages:
        err("BPF009", p.name, f"first stage '{p.first_stage}' does not exist")
        return out
    if p.stages[p.first_stage].table != p.primary_table:
        err("BPF012", p.name, "the first stage must use the primary table of the process")

    for s in p.stages.values():
        w = f"stage '{s.name}'"
        if len(s.steps) > MAX_STEPS:
            err("BPF002", w, f"{len(s.steps)} steps; the limit is {MAX_STEPS} per stage")
        for t in s.targets():
            if t not in p.stages:
                err("BPF009", w, f"points to unknown stage '{t}'")
        for st in s.steps:
            if st.required and st.type == "twoOptions":
                warn("BPF008", f"{w}, step {st.column}",
                     "a required Two Options step only passes when it is Yes; use a Choice if No is also valid")
            if st.type == "choice" and st.required and not st.valid:
                warn("BPF013", f"{w}, step {st.column}", "required choice without a list of valid values to test")
        if s.exit_workflows and s.next is None:
            warn("BPF011", w, "a workflow on Stage Exit of the last stage never runs: use a global workflow "
                              "(Process Completed / Process Abandoned)")
        if isinstance(s.next, dict):
            _check_condition(p, s, err, warn)

    reachable = _reachable(p)
    for sid, s in p.stages.items():
        if sid not in reachable:
            err("BPF009", f"stage '{s.name}'", "is not reachable from the first stage")
    if _has_cycle(p):
        err("BPF010", p.name, "forward transitions form a loop; going back is a user action (Set Active), not a transition")
    _check_merges(p, err)
    depth = _branch_depth(p)
    if depth > SAFE_BRANCH_DEPTH:
        warn("BPF014", p.name, f"branch depth {depth}: Learn says five levels in one tutorial and ten in another")
    return out


def _check_condition(p: Process, s, err, warn) -> None:
    cond = s.next["condition"]
    w = f"condition after '{s.name}'"
    if cond.get("op") not in ("and", "or"):
        err("BPF005", w, "operator must be 'and' or 'or'")
    ops = {r.get("join") for r in cond.get("rules", []) if r.get("join")}
    if len(ops | {cond.get("op")}) > 1:
        err("BPF005", w, "a rule can combine conditions with AND or OR, not both")
    columns = {st.column for st in s.steps}
    for r in cond.get("rules", []):
        if r["column"] not in columns:
            err("BPF006", w, f"rule on '{r['column']}', which is not a step of '{s.name}'. "
                              "A branching rule must be based on steps of the stage that immediately precedes it: "
                              "add the column as a step (it can be optional)")


def _reachable(p: Process) -> set[str]:
    seen, todo = set(), [p.first_stage]
    while todo:
        x = todo.pop()
        if x in seen or x not in p.stages:
            continue
        seen.add(x)
        todo.extend(p.stages[x].targets())
    return seen


def _has_cycle(p: Process) -> bool:
    state: dict[str, int] = {}

    def visit(x):
        state[x] = 1
        for t in p.stages[x].targets():
            if t not in p.stages:
                continue
            if state.get(t) == 1 or (t not in state and visit(t)):
                return True
        state[x] = 2
        return False

    return visit(p.first_stage)


def _paths(p: Process, sid: str | None = None, acc=()):
    sid = sid or p.first_stage
    acc = acc + (sid,)
    targets = p.stages[sid].targets()
    if not targets:
        yield acc
    for t in targets:
        if t in p.stages and t not in acc:
            yield from _paths(p, t, acc)


def _check_merges(p: Process, err) -> None:
    """Peer branches must merge into a single stage, or every branch must end the process (Learn: branching)."""
    for s in p.stages.values():
        if not isinstance(s.next, dict):
            continue
        paths = {label: list(_paths(p, s.next[label])) for label in ("yes", "no")}
        reach = {label: {n for path in ps for n in path} for label, ps in paths.items()}
        shared = reach["yes"] & reach["no"]
        if not shared:
            continue  # both branches end the process on their own
        every = [set(path) for ps in paths.values() for path in ps]
        if not any(all(m in path for path in every) for m in shared):
            err("BPF007", f"condition after '{s.name}'",
                "peer branches must merge into a single stage (or all end the process); "
                "a branch cannot merge and end the process at the same time")


def _branch_depth(p: Process) -> int:
    def depth(sid, seen=()):
        if sid not in p.stages or sid in seen:
            return 0
        s = p.stages[sid]
        if s.next is None:
            return 0
        if isinstance(s.next, str):
            return depth(s.next, seen + (sid,))
        return 1 + max(depth(s.next["yes"], seen + (sid,)), depth(s.next["no"], seen + (sid,)))
    return depth(p.first_stage)


def validate_set(processes: list[Process]) -> list[Finding]:
    """Cross-process rule: at most 10 active BPFs per table (default Organization setting)."""
    out = []
    per_table: dict[str, int] = {}
    for p in processes:
        per_table[p.primary_table] = per_table.get(p.primary_table, 0) + 1
    for table, n in per_table.items():
        if n > MAX_ACTIVE_PER_TABLE:
            out.append(Finding("error", "BPF015", table,
                               f"{n} active processes; the default maximum is {MAX_ACTIVE_PER_TABLE} per table "
                               "(Organization.MaximumActiveBusinessProcessFlowsAllowedPerEntity)"))
    return out
