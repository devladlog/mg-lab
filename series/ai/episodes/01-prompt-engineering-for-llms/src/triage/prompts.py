"""Versioned prompts for Contoso helpdesk ticket triage.

v1 is the prompt most teams start with. v2 applies the techniques from Microsoft Learn "Prompt engineering techniques"
and "System message design": a system message with role, rules and explicit fallback behaviour, few-shot examples as
user/assistant pairs after the system message, spotlighting for the untrusted ticket text, and structured outputs.
Prompts are code: version them, review them, and evaluate every change against the same dataset.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .schema import response_format
from .spotlight import SPOTLIGHT_RULES, spotlight

Message = dict[str, str]

SYSTEM_V2 = f"""You are the triage assistant for the Contoso IT helpdesk. You classify one ticket at a time.

## Categories
- access: sign-in, passwords, MFA, permissions, licences
- hardware: laptops, docks, monitors, printers, phones
- software: installed apps, Office, line-of-business apps, updates
- network: Wi-Fi, VPN, internet, DNS, file shares unreachable
- other: anything else

## Priorities
- P1: many people blocked, or a security incident (phishing clicked, lost device with company data)
- P2: one person fully blocked from working
- P3: degraded but a workaround exists
- P4: question, request, or cosmetic issue

## Rules
- Summarise the problem in one sentence of at most 20 words. Never copy names, emails or phone numbers.
- If the ticket is too vague to classify, use category "other", priority "P3" and set needs_human to true.
- Set needs_human to true for every P1 and every possible security incident.
- {SPOTLIGHT_RULES}
"""

# Few-shot examples: chosen to cover edge cases (security = P1, vague = needs_human), per Learn's advice.
FEW_SHOT: list[tuple[str, dict[str, Any]]] = [
    (
        "Since this morning nobody on the 3rd floor can connect to the Wi-Fi, we're all on phone hotspots.",
        {"category": "network", "priority": "P1", "summary": "Whole third floor cannot connect to Wi-Fi.",
         "needs_human": True, "injection_suspected": False},
    ),
    (
        "I clicked a link in an email about my parcel and typed my password. Now I'm worried.",
        {"category": "access", "priority": "P1", "summary": "User entered password on a suspected phishing page.",
         "needs_human": True, "injection_suspected": False},
    ),
    (
        "it doesn't work",
        {"category": "other", "priority": "P3", "summary": "Unspecified problem; details needed.",
         "needs_human": True, "injection_suspected": False},
    ),
]


@dataclass(frozen=True)
class Prompt:
    version: str
    description: str
    build_messages: Callable[[str], list[Message]]
    response_format: dict[str, Any] | None = field(default=None)


def _v1_messages(ticket: str) -> list[Message]:
    return [{"role": "user", "content": f"Classify this IT ticket and give category, priority and a summary as JSON.\n\n{ticket}"}]


def _v2_messages(ticket: str) -> list[Message]:
    messages: list[Message] = [{"role": "system", "content": SYSTEM_V2}]
    for example_text, example_answer in FEW_SHOT:
        messages.append({"role": "user", "content": spotlight(example_text)})
        messages.append({"role": "assistant", "content": json.dumps(example_answer)})
    messages.append({"role": "user", "content": spotlight(ticket)})
    return messages


PROMPTS: dict[str, Prompt] = {
    "v1": Prompt("v1", "one-line instruction, ticket pasted in, free-form JSON", _v1_messages, None),
    "v2": Prompt("v2", "system message + few-shot + spotlighting + structured outputs", _v2_messages, response_format()),
}


def get_prompt(version: str) -> Prompt:
    try:
        return PROMPTS[version]
    except KeyError:
        raise ValueError(f"Unknown prompt version '{version}'. Known: {', '.join(PROMPTS)}") from None
