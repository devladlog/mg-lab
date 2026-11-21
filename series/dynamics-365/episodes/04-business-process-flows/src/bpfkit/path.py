"""Stage navigation rules, as pure functions (no network), following "Work with business process flows using code":

- An instance stores its active stage (activestageid) and `traversedpath`: the comma-separated ids of the stages
  visited so far, ending with the active stage.
- Move only to the NEXT stage of the active path, or back to the PREVIOUS one. The active path comes from
  RetrieveActivePath, which evaluates the branch conditions against the record's current data.
- Finished (statecode 0, statuscode 2) is only possible at the last stage; Aborted is 1/3; Active is 0/1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

ACTIVE, FINISHED, ABORTED = (0, 1), (0, 2), (1, 3)   # (statecode, statuscode)


class StageMoveError(ValueError):
    pass


def norm(guid: Optional[str]) -> str:
    return (guid or "").strip().strip("{}").lower()


def parse_traversed(traversed: Optional[str]) -> List[str]:
    return [norm(s) for s in (traversed or "").split(",") if s.strip()]


def format_traversed(ids: Sequence[str]) -> str:
    return ",".join(norm(i) for i in ids)


@dataclass(frozen=True)
class Move:
    target: str            # processstageid to activate
    traversedpath: str     # new traversed path to send with it

    def payload(self) -> Dict[str, str]:
        return {"activestageid@odata.bind": f"/processstages({self.target})", "traversedpath": self.traversedpath}


def _check_consistent(active_path: Sequence[str], current: str, traversed: List[str]) -> None:
    if current not in active_path:
        raise StageMoveError("the active stage isn't on the active path: the record's data changed the branch; "
                             "fix the data or move back first")
    if not traversed or traversed[-1] != current:
        raise StageMoveError("traversedpath doesn't end with the active stage: instance is inconsistent, "
                             "don't patch it blindly")


def forward(active_path: Sequence[str], current: str, traversed_text: Optional[str]) -> Move:
    path = [norm(s) for s in active_path]
    cur, traversed = norm(current), parse_traversed(traversed_text)
    _check_consistent(path, cur, traversed)
    i = path.index(cur)
    if i == len(path) - 1:
        raise StageMoveError("already at the last stage: use 'finish' instead")
    nxt = path[i + 1]
    return Move(nxt, format_traversed(traversed + [nxt]))


def back(active_path: Sequence[str], current: str, traversed_text: Optional[str]) -> Move:
    path = [norm(s) for s in active_path]
    cur, traversed = norm(current), parse_traversed(traversed_text)
    _check_consistent(path, cur, traversed)
    if len(traversed) < 2:
        raise StageMoveError("already at the first stage")
    prev = traversed[-2]
    return Move(prev, format_traversed(traversed[:-1]))


def can_finish(active_path: Sequence[str], current: str) -> bool:
    return bool(active_path) and norm(active_path[-1]) == norm(current)


def state_name(statecode: Optional[int], statuscode: Optional[int]) -> str:
    return {ACTIVE: "Active", FINISHED: "Finished", ABORTED: "Aborted"}.get((statecode, statuscode),
                                                                             f"state {statecode}/{statuscode}")
