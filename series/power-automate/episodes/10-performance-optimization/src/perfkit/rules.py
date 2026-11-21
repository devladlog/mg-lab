"""Static performance rules for a cloud flow. Each one cites the Learn page it comes from (README has the links)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from flowkit.lint import definition_of, iter_actions

MAX_CONCURRENCY = 50          # Learn, limits: Apply to each concurrency 1 to 50, default 1
LOW_PAGINATED_ITEMS = 5000    # Learn, limits: paginated items and Apply to each items, 5,000 for the Low profile
VARIABLE_TYPES = {"SetVariable", "IncrementVariable", "DecrementVariable", "AppendToArrayVariable", "AppendToStringVariable"}
CHANGING_TYPES = {"IncrementVariable", "DecrementVariable", "AppendToArrayVariable", "AppendToStringVariable", "SetVariable"}


@dataclass
class Finding:
    level: str  # error | warning
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.where}: {self.message}"


def op(action: dict) -> str | None:
    inputs = action.get("inputs")
    return (inputs or {}).get("host", {}).get("operationId") if isinstance(inputs, dict) else None


def concurrency(action: dict) -> int:
    """Degree of parallelism of an Apply to each: 1 unless runtimeConfiguration.concurrency.repetitions says otherwise."""
    return int(((action.get("runtimeConfiguration") or {}).get("concurrency") or {}).get("repetitions") or 1)


def _body_refs(text: str) -> set[str]:
    return set(re.findall(r"(?:body|outputs)\('([^']+)'\)", text or ""))


def _param(action: dict, name: str):
    return (action.get("inputs") or {}).get("parameters", {}).get(name)


def analyze(flow: dict) -> list[Finding]:
    definition = definition_of(flow)
    actions = definition.get("actions", {})
    flat = list(iter_actions(actions))
    by_name = {name: a for name, a, *_ in flat}
    out: list[Finding] = []

    for name, action, depth, loops, scope, where in flat:
        t = action.get("type")

        if t == "Foreach" and not loops:  # Learn: nested loops always run sequentially, only the top level counts
            c = concurrency(action)
            inner = [(n, a) for n, a, *_ in iter_actions(action.get("actions", {}))]
            calls = [n for n, a in inner if a.get("type") == "OpenApiConnection"]
            source = next(iter(_body_refs(action.get("foreach", ""))), None)
            src_action = by_name.get(source)

            if calls and c == 1:
                out.append(Finding("warning", "P01", where,
                    f"Apply to each runs one item at a time (concurrency default is 1; 1-{MAX_CONCURRENCY} allowed) "
                    f"and calls {', '.join(calls)} for every item. Turn concurrency on if the items don't depend on each other."))

            if src_action is not None and op(src_action) in ("GetItems", "GetFileItems") and not _param(src_action, "$filter"):
                if any(a.get("type") == "If" for a in action.get("actions", {}).values()):
                    out.append(Finding("warning", "P02", where,
                        f"{source} reads every item (no $filter) and the loop tests each one with a condition. "
                        "Filter at the source with an OData $filter instead of testing inside Apply to each."))

            if src_action is not None and op(src_action) in ("GetItems", "GetFileItems"):
                for n, a in inner:
                    if op(a) in ("GetItem", "GetFileItem") and _param(a, "table") == _param(src_action, "table"):
                        out.append(Finding("warning", "P03", f"{where}.{n}",
                            f"re-reads an item of the same list that {source} already returned: use the item's own fields"))

            changers = [(n, a) for n, a in inner if a.get("type") in CHANGING_TYPES]
            for n, a in changers:
                if c > 1:
                    out.append(Finding("error", "P04", f"{where}.{n}",
                        f"{a['type']} inside a loop that runs {c} items at once: iterations share one variable, "
                        "so the result can be unpredictable. Compute the value after the loop (length(), a Select) instead."))
                else:
                    out.append(Finding("warning", "P05", f"{where}.{n}",
                        "variables lock exclusively and slow a loop down; count with length() or a Select after the loop."))

            only_appends = inner and all(a.get("type") == "AppendToArrayVariable" for _, a in inner)
            if only_appends:
                out.append(Finding("warning", "P06", where, "the loop only appends to an array: a Select does that without a loop"))

            if c > MAX_CONCURRENCY or c < 1:
                out.append(Finding("error", "P07", where, f"concurrency {c} is outside 1-{MAX_CONCURRENCY}"))

        if t == "OpenApiConnection" and op(action) in ("GetItems", "GetFileItems"):
            pag = (action.get("runtimeConfiguration") or {}).get("paginationPolicy", {}).get("minimumItemCount")
            if pag is None and not _param(action, "$top"):
                out.append(Finding("warning", "P08", where,
                    "Get items without pagination and without a Top Count returns the first page only (default item limit 100)"))
            if pag is not None and int(pag) > LOW_PAGINATED_ITEMS:
                out.append(Finding("warning", "P09", where,
                    f"pagination threshold {pag} is above 5,000, the cap for the Low performance profile (trial licences, "
                    "Microsoft 365 plans)"))

    # P10: frequent polling triggers without a trigger condition
    for tname, trig in definition.get("triggers", {}).items():
        o = op(trig)
        rec = trig.get("recurrence") or {}
        if o in ("GetOnNewItems", "GetOnUpdatedItems", "GetOnChangedItems", "GetOnNewFileItems") and not trig.get("conditions"):
            out.append(Finding("warning", "P10", f"triggers.{tname}",
                "no trigger condition: every item starts a run (and costs requests) even when the flow ends up doing nothing"))
    return out
