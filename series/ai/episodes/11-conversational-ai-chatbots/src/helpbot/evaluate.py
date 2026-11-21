"""Scripted multi-turn dialogues against the real bot. Checks look at the session state (tickets, handoff) first and
at the words of the last reply second, because a chatbot's real behaviour is what it DID, not only what it said."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .bot import Bot, Reply
from .session import Session

SCENARIOS_FILE = Path(__file__).resolve().parents[2] / "data" / "scenarios.json"


def load_scenarios(path=None) -> list[dict]:
    return json.loads(Path(path or SCENARIOS_FILE).read_text(encoding="utf-8"))


@dataclass
class Result:
    scenario: str
    mode: str
    passed: bool
    informational: bool
    problems: list[str]
    model_calls: int = 0
    prompt_tokens: int = 0
    first_call_error_pct: list[float] = field(default_factory=list)   # (estimate - billed) / billed per turn
    error: str | None = None


def check(scn: dict, session: Session, replies: list[Reply]) -> list[str]:
    """Returns the list of problems (empty = pass). Unknown check names are an error, not a silent pass."""
    c, last, problems = scn["checks"], replies[-1], []
    low = last.text.lower()
    known = {"tickets", "ticket_fields", "ticket_id_in_last_reply", "handoff", "model_calls_total_max",
             "last_reply_has_any", "last_reply_has_none"}
    for unknown in set(c) - known:
        problems.append(f"unknown check {unknown!r}")
    if "tickets" in c and len(session.tickets) != c["tickets"]:
        problems.append(f"expected {c['tickets']} ticket(s), found {len(session.tickets)}")
    for k, v in c.get("ticket_fields", {}).items():
        if not session.tickets or session.tickets[0].get(k) != v:
            problems.append(f"ticket field {k}: expected {v!r}, got {session.tickets[0].get(k) if session.tickets else None!r}")
    if c.get("ticket_id_in_last_reply") and not (session.tickets and session.tickets[0]["ticket_id"] in last.text):
        problems.append("the last reply does not quote the ticket id that the tool returned")
    if "handoff" in c and (session.state == "handoff") != c["handoff"]:
        problems.append(f"expected handoff={c['handoff']}, state is {session.state!r}")
    if "model_calls_total_max" in c and sum(r.model_calls for r in replies) > c["model_calls_total_max"]:
        problems.append(f"model calls {sum(r.model_calls for r in replies)} > {c['model_calls_total_max']}")
    if "last_reply_has_any" in c and not any(w.lower() in low for w in c["last_reply_has_any"]):
        problems.append(f"the last reply contains none of {c['last_reply_has_any']}")
    for w in c.get("last_reply_has_none", []):
        if w.lower() in low:
            problems.append(f"the last reply contains {w!r}")
    for t in session.tickets:                                   # invariant for EVERY scenario
        if not t["contact"].endswith("@contoso.com"):
            problems.append(f"ticket {t['ticket_id']} has an outside contact")
    return problems


def run_scenario(bot: Bot, scn: dict) -> tuple[Session, list[Reply]]:
    s, replies = Session(), []
    for text in scn["turns"]:
        replies.append(bot.reply(s, text))
    return s, replies


def evaluate(make_bot, scenarios: list[dict], modes=("summary", "window"), gate_mode="summary", only=None) -> list[Result]:
    """make_bot(mode, scenario) -> Bot. A scenario listed informational for a mode is reported but cannot fail the gate."""
    results = []
    for scn in scenarios:
        if only and scn["id"] not in only:
            continue
        for mode in modes:
            info = mode != gate_mode or mode in scn.get("informational_modes", [])
            try:
                s, replies = run_scenario(make_bot(mode, scn), scn)
                problems = check(scn, s, replies)
                err = [100.0 * (r.estimated_prompt_tokens - r.first_prompt_tokens) / r.first_prompt_tokens
                       for r in replies if r.first_prompt_tokens and r.estimated_prompt_tokens]
                results.append(Result(scn["id"], mode, not problems, info, problems,
                                      sum(r.model_calls for r in replies), sum(r.prompt_tokens for r in replies), err))
            except Exception as e:                                   # a failed call is a failed scenario, not a crash
                results.append(Result(scn["id"], mode, False, info, [], error=f"{type(e).__name__}: {e}"))
    return results


def gate(results: list[Result]) -> tuple[bool, list[str]]:
    bad = [f"{r.scenario} [{r.mode}]: " + (r.error or "; ".join(r.problems)) for r in results if not r.passed and not r.informational]
    return not bad, bad


def format_report(results: list[Result]) -> str:
    rows = ["scenario                 mode     result   calls  prompt tok  est. error", "-" * 70]
    for r in results:
        label = "pass" if r.passed else ("INFO-fail" if r.informational else "FAIL")
        e = f"{sum(r.first_call_error_pct) / len(r.first_call_error_pct):+.0f}%" if r.first_call_error_pct else "n/a"
        rows.append(f"{r.scenario:<24} {r.mode:<8} {label:<9} {r.model_calls:>4} {r.prompt_tokens:>10}  {e:>9}")
        for p in r.problems + ([r.error] if r.error else []):
            rows.append(f"    - {p}")
    ok, bad = gate(results)
    rows.append("")
    rows.append("RESULT: " + ("PASS" if ok else "FAIL (" + str(len(bad)) + " gated scenario(s) failed)"))
    return "\n".join(rows)
