"""python -m helpbot chat | evaluate"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import evaluate as ev
from .bot import Bot
from .client import make_client
from .session import Session, SessionStore


def _common(p):
    p.add_argument("--endpoint", default=os.environ.get("HELPBOT_ENDPOINT"), help="https://<name>.openai.azure.com")
    p.add_argument("--deployment", default="chat", help="deployment name of the chat model (gpt-4.1-mini)")
    p.add_argument("--history-budget", type=int, default=int(os.environ.get("HELPBOT_BUDGET", "1500")),
                   help="estimated tokens of history sent per request (summary + newest whole turns)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="helpbot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chat", help="talk to the bot in the terminal (streamed); --script feeds the user lines from a file")
    _common(c)
    c.add_argument("--session", default=None, help="session id to resume (stored under --store)")
    c.add_argument("--store", default="build/sessions")
    c.add_argument("--memory", choices=["summary", "window"], default="summary")
    c.add_argument("--script", default=None, help="text file, one user message per line")
    e = sub.add_parser("evaluate", help="run the scripted dialogues in both memory modes; exit 1 if the gated mode fails")
    _common(e)
    e.add_argument("--scenarios", default=None)
    e.add_argument("--only", action="append")
    return ap


def _client(a):
    if not a.endpoint:
        raise SystemExit("--endpoint or HELPBOT_ENDPOINT is required")
    return make_client(a.endpoint)


def _chat(a) -> int:
    store = SessionStore(a.store)
    s = (store.load(a.session) if a.session else None) or Session(**({"id": a.session} if a.session else {}))
    bot = Bot(_client(a), a.deployment, memory_mode=a.memory, history_budget=a.history_budget)
    lines = iter(Path(a.script).read_text(encoding="utf-8").splitlines()) if a.script else None
    print(f"session {s.id} · memory={a.memory} · budget={a.history_budget} · empty line to quit")
    while True:
        try:
            text = next(lines).strip() if lines is not None else input("you> ").strip()
        except (StopIteration, EOFError):
            break
        if not text:
            break
        if lines is not None:
            print(f"you> {text}")
        print("bot> ", end="", flush=True)
        streamed: list[str] = []

        def show(tok):
            streamed.append(tok)
            print(tok, end="", flush=True)

        r = bot.reply(s, text, on_token=show)
        if "".join(streamed).strip() != r.text.strip():          # a rule answered, or a streamed answer was replaced
            print(("\n" if streamed else "") + r.text, end="")
        print()
        print(f"     [calls={r.model_calls} prompt_tokens={r.prompt_tokens} est={r.estimated_prompt_tokens}"
              f" folded={r.folded_turns} state={s.state}" + (f" notes={'; '.join(r.notes)}" if r.notes else "") + "]")
        store.save(s)
    for t in s.tickets:
        print(f"ticket {t['ticket_id']}: {t['urgency']} · {t['product']} · {t['contact']}")
    if s.summary:
        print("summary:", s.summary)
    return 0


def _evaluate(a) -> int:
    client = _client(a)
    results = ev.evaluate(lambda mode, scn: Bot(client, a.deployment, memory_mode=mode,
                                                history_budget=scn.get("history_budget", a.history_budget)),
                          ev.load_scenarios(a.scenarios), only=a.only)
    print(ev.format_report(results))
    return 0 if ev.gate(results)[0] else 1


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return _chat(a) if a.cmd == "chat" else _evaluate(a)
    except SystemExit:
        raise
    except Exception as e:                                       # one clear line instead of a stack trace on camera
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
