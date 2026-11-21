"""Lint a prompt before you give it to Copilot in the Power Automate designer.

Every rule comes from two Microsoft Learn pages:
  * "Create your first cloud flow using Copilot" (section "How to write a good prompt")
  * "Get the most from Copilot in Power Automate designer" (what works, what does not, tips)
Two modes, because the pages give different advice for them:
  create = the first prompt on the Home page ("Create with Copilot"), where Learn says to describe the flow in detail;
  edit   = a message to the Copilot pane inside the designer, where Learn says one request per message.
"""
from __future__ import annotations

import re

from .findings import Finding

# Connectors Learn mentions in its prompt examples ("Outlook, Teams, Forms, or other") plus common standard ones.
CONNECTORS = (
    "outlook", "office 365", "teams", "forms", "sharepoint", "onedrive", "excel", "planner", "approvals", "approval",
    "dataverse", "to do", "outlook calendar", "calendar", "notification", "mobile notification", "x ", "twitter",
    "email", "e-mail", "list",
)
TRIGGER_START = re.compile(r"^\s*(when|every|each|on|if|at|once|daily|weekly|monthly|whenever)\b", re.I)
TRIGGER_ANYWHERE = re.compile(r"\b(when|whenever|every|each (day|week|month|monday|tuesday|wednesday|thursday|friday)|runs? (daily|weekly|monthly))\b", re.I)
ACTION_VERBS = ("send", "post", "update", "create", "get", "check", "wait", "add", "delete", "remove", "copy", "move",
                "approve", "notify", "start", "set", "append", "write", "email")
VAGUE = re.compile(r"^\s*(fix|repair|improve|optimi[sz]e|make)\b.{0,25}\b(flow|it|this|work)\b", re.I)
DEBUG = re.compile(r"\b(why did|why does|why is|why was|debug|what went wrong|failed (at|yesterday|today)|error code)\b", re.I)
DATA = re.compile(r"\b(what columns|which columns|does my (list|table)|is the (email|address|value) in my|in my (sharepoint|dataverse|sql))\b", re.I)


def lint_prompt(text: str, mode: str = "create") -> list[Finding]:
    if mode not in ("create", "edit"):
        raise ValueError("mode must be 'create' or 'edit'")
    findings: list[Finding] = []
    prompt = text.strip()
    if not prompt:
        return [Finding("PL000", "error", "prompt", "The prompt is empty.")]
    lowered = prompt.lower()

    if mode == "create":
        if not (TRIGGER_START.match(prompt) or TRIGGER_ANYWHERE.search(prompt)):
            findings.append(Finding("PL001", "warning", "prompt",
                "No trigger. Learn: write it as 'When X happens, do Y' so Copilot can pick the trigger."))
        if not any(c in lowered for c in CONNECTORS):
            findings.append(Finding("PL002", "warning", "prompt",
                "No connector named. Learn: if possible, mention the connector (Outlook, Teams, Forms, SharePoint ...)."))
        if len(prompt.split()) < 6:
            findings.append(Finding("PL003", "warning", "prompt",
                "Very short. Learn: be as specific as possible; 'I want to process an email' is the generic example to avoid."))
    else:
        steps = _count_steps(lowered)
        if steps >= 3:
            findings.append(Finding("PL004", "warning", "prompt",
                f"About {steps} steps in one message. Learn: give one instruction, check the result, then the next; "
                "Copilot loses accuracy across long chains."))
        if VAGUE.match(prompt):
            findings.append(Finding("PL005", "error", "prompt",
                "Too vague. Learn: Copilot cannot see what is wrong, so 'fix my flow' means nothing to it; say exactly what to change."))
        if not re.match(r"^\s*(add|change|remove|explain|move|delete|replace|update|what|how|rename|wrap|set|use)\b", lowered):
            findings.append(Finding("PL006", "info", "prompt",
                "Learn: start with an action verb (Add, Change, Remove, Explain, Move); they map to operations Copilot can perform."))

    if DEBUG.search(prompt):
        findings.append(Finding("PL007", "warning", "prompt",
            "Asks Copilot to debug a run. Learn: the designer's Copilot has no access to run history or error logs; "
            "use Troubleshoot in Copilot on the run page, or paste the full error message into an external AI."))
    if DATA.search(prompt):
        findings.append(Finding("PL008", "warning", "prompt",
            "Asks about your data. Learn: Copilot cannot query SharePoint lists, Dataverse tables or other live data; "
            "check the data yourself and give Copilot the exact field names."))
    return findings


def _count_steps(lowered: str) -> int:
    """Rough count of sequential steps: verbs that start a clause after a comma, 'then' or 'and'."""
    clauses = re.split(r",|;|\bthen\b|\band then\b|\bafter that\b|\band\b", lowered)
    n = 0
    for c in clauses:
        words = c.strip().split()
        if words and (words[0] in ACTION_VERBS or (len(words) > 1 and words[0] in ("i", "to") and words[1] in ACTION_VERBS)):
            n += 1
    return n
