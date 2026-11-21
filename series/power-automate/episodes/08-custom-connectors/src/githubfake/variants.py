"""Our earlier drafts, as small changes to the connector or the flow. Each one has a test."""
import copy
import json

from connectorkit import Connector


def _copy(c: Connector) -> Connector:
    return Connector(copy.deepcopy(c.definition), copy.deepcopy(c.properties), dict(c.settings), c.size_bytes)


def no_body_defaults(c: Connector) -> Connector:
    """Draft 1: the hook body without defaults. GitHub's own defaults are events [push] and content type form."""
    out = _copy(c)
    props = out.definition["definitions"]["HookRequest"]["properties"]
    props["events"].pop("default")
    props["config"]["properties"]["content_type"].pop("default")
    out.definition["definitions"]["HookRequest"]["required"].remove("events")
    props["config"]["required"].remove("content_type")   # nothing makes the platform send them any more
    return out


def no_delete_operation(c: Connector) -> Connector:
    """Draft 2: only the trigger, no operation to delete the webhook."""
    out = _copy(c)
    del out.definition["paths"]["/repos/{owner}/{repo}/hooks/{hook_id}"]
    return out


def no_trigger_condition(flow: dict) -> dict:
    """Draft 3: the trigger without the 'opened' condition."""
    out = copy.deepcopy(flow)
    for t in out["properties"]["definition"]["triggers"].values():
        t.pop("conditions", None)
    return out
