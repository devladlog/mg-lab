"""Checks for adaptive cards posted by the Microsoft Teams connector, from Microsoft Learn:

- Teams connector, known issues: "the message size limit is approximately 28 KB ... If the message size
  exceeds 28 KB, the action fails with the error 'Request Entity too large'"; "A single message can @mention
  only up to 20 users and 20 tags"; posting to a private channel "currently isn't supported".
- Overview of adaptive cards for Microsoft Teams, known issues: you can't collect data unless the card is
  posted with a *wait for a response* action, and Action.Submit on other cards shows an error; a wait-for-
  response card "can only be submitted once".
- Copilot Studio, proactive messages (same Teams action): "Power Automate doesn't support Adaptive Cards that
  use the templating feature", and submitActionId is "the title of the action the user selected".
"""
from __future__ import annotations

import json
import re

MAX_MESSAGE_BYTES = 28 * 1024     # "approximately 28 KB": we treat 28 KiB as the line
MAX_MENTIONS = 20


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def card_problems(card_text: str, waits_for_response: bool) -> list[str]:
    """Problems that make Teams or Power Automate reject or mishandle the card. Empty list = OK."""
    try:
        card = json.loads(card_text)
    except (TypeError, json.JSONDecodeError) as e:
        return [f"card isn't valid JSON: {e}"]
    problems = []
    if not isinstance(card, dict) or card.get("type") != "AdaptiveCard":
        problems.append("the root object must have \"type\": \"AdaptiveCard\"")
        return problems
    if not isinstance(card.get("version"), str):
        problems.append("the card has no version string")
    if len(card_text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        problems.append(f"card is {len(card_text.encode('utf-8'))} bytes; the Teams message limit is about 28 KB "
                        f"(Request Entity too large)")
    if re.search(r"\$\{[^}]*\}", card_text) or "$data" in card:
        problems.append("adaptive card templating (${...} / $data) isn't supported by Power Automate")
    nodes = list(walk(card))
    ids = [n["id"] for n in nodes if isinstance(n.get("type"), str) and n["type"].startswith("Input.") and "id" in n]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"input id {dup!r} is used twice")
    submits = [n for n in nodes if n.get("type") == "Action.Submit"]
    titles = [s.get("title") for s in submits]
    for dup in sorted({t for t in titles if titles.count(t) > 1 and t}):
        problems.append(f"two Action.Submit buttons are titled {dup!r}: submitActionId is the title, so the flow "
                        f"can't tell them apart")
    if submits and not waits_for_response:
        problems.append("Action.Submit only works on cards posted with 'Post adaptive card and wait for a response'")
    if waits_for_response and not submits:
        problems.append("a wait-for-response card needs at least one Action.Submit, or nobody can answer it")
    return problems


def mention_count(message_html: str) -> int:
    return len(re.findall(r"<at\b", message_html or "", flags=re.IGNORECASE))
