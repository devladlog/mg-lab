"""Earlier drafts of the flow, kept as transformations so the problems they had stay reproducible."""
from __future__ import annotations

import copy
import json

from flowkit.lint import definition_of


def card_as_string_template(flow: dict) -> dict:
    """Draft 1: the card JSON pasted into the action's Message box, with dynamic content inside the text."""
    f = copy.deepcopy(flow)
    acts = definition_of(f)["actions"]
    card = acts["Build_card"]["inputs"]
    acts["Ask_on_call"]["inputs"]["parameters"]["body/body/messageBody"] = json.dumps(card, indent=2)
    return f


def all_posts_as_flow_bot(flow: dict) -> dict:
    """Draft 2: every Teams post as Flow bot, including the 'who took it' announcement."""
    f = copy.deepcopy(flow)
    acts = definition_of(f)["actions"]
    acts["Route_response"]["cases"]["Take_it"]["actions"]["Announce_owner"]["inputs"]["parameters"]["poster"] = "Flow bot"
    acts["Escalate_to_lead"]["actions"]["Escalate_in_channel"]["inputs"]["parameters"]["poster"] = "Flow bot"
    return f
