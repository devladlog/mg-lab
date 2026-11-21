"""A tiny executor for business-rules.yaml, so the rules can be tested without a tenant.

It models what Learn documents for business rules (conditions on columns, then/else actions, scopes) and nothing
more: it is NOT the Dataverse engine, and it can't prove how the designer behaves. It proves that the rules we wrote down
mean what we say they mean, and that no rule uses an action its scope doesn't support.
"""
from __future__ import annotations

import yaml

# Learn: "Create business rules to apply logic in a model-driven app form" (Action / Applies to table)
ACTIONS_EVERY_SCOPE = {"set_value", "set_default_value", "show_error"}
ACTIONS_FORM_ONLY = {"lock", "unlock", "set_visibility", "set_business_required", "recommendation"}
SCOPES = ("table", "all_forms")


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]


def valid_scope(scope):
    return scope in SCOPES or (isinstance(scope, str) and scope.startswith("form:"))


def allowed_actions(scope):
    return ACTIONS_EVERY_SCOPE if scope == "table" else ACTIONS_EVERY_SCOPE | ACTIONS_FORM_ONLY


def _leaf(cond, record):
    v = record.get(cond["column"])
    op = cond["op"]
    if op == "eq":
        return v == cond["value"]
    if op == "ne":
        return v != cond["value"]
    if op == "isnull":
        return v is None
    if op == "notnull":
        return v is not None
    if op == "gt":
        return v is not None and v > cond["value"]
    if op == "lt":
        return v is not None and v < cond["value"]
    raise ValueError(f"unknown operator {op}")


def evaluate(cond, record):
    if "all" in cond:
        return all(evaluate(c, record) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, record) for c in cond["any"])
    return _leaf(cond, record)


def conditions_columns(cond):
    if "all" in cond or "any" in cond:
        return [c for sub in cond.get("all", cond.get("any")) for c in conditions_columns(sub)]
    return [cond["column"]]


def run(rules, table, record, client="form", is_new=False):
    """Apply every rule of `table` to `record`. client: 'form' (model-driven form) or 'server' (create/update through the API,
    which is what a canvas app does). Returns a state dict: values, required, visible, locked, errors."""
    state = {"values": dict(record), "required": {}, "visible": {}, "locked": {}, "errors": []}
    for r in rules:
        if r["table"] != table:
            continue
        if client == "server" and r["scope"] != "table":
            continue            # all_forms / form rules never run on the server
        branch = r["then"] if evaluate(r["when"], state["values"]) else r.get("otherwise", [])
        for a in branch:
            act, col = a["action"], a.get("column")
            if client == "server" and act not in ACTIONS_EVERY_SCOPE:
                continue        # model-driven-only actions are ignored server side (Learn)
            if act == "set_value":
                state["values"][col] = a["value"]
            elif act == "set_default_value":
                if state["values"].get(col) is None:
                    state["values"][col] = a["value"]
            elif act == "show_error":
                state["errors"].append((col, a["message"]))
            elif act == "lock":
                state["locked"][col] = True
            elif act == "unlock":
                state["locked"][col] = False
            elif act == "set_visibility":
                state["visible"][col] = a["visible"]
            elif act == "set_business_required":
                state["required"][col] = a["required"]
    return state
