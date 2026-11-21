"""Evaluate prompt versions against a labelled dataset and print a scorecard.

    python -m triage.evaluate --data data/tickets.jsonl --prompt v1 --prompt v2 \
        --deployment triage-mini --model gpt-5-mini            # live: needs an Azure OpenAI deployment
    python -m triage.evaluate --data data/tickets.jsonl --prompt v2 --dry-run   # offline: prints the request

Authentication is Microsoft Entra ID only (DefaultAzureCredential): the identity needs the
"Cognitive Services OpenAI User" role on the resource. Set AZURE_OPENAI_ENDPOINT to https://<resource>.openai.azure.com
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from jsonschema import Draft202012Validator

from .prompts import get_prompt
from .request import build_request
from .schema import TRIAGE_SCHEMA

_VALIDATOR = Draft202012Validator(TRIAGE_SCHEMA)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

# complete(body) -> (content, usage, finish_reason)
CompleteFn = Callable[[dict[str, Any]], tuple[str | None, dict[str, int], str]]


@dataclass
class Ticket:
    id: str
    text: str
    category: str
    priority: str
    attack: bool = False


@dataclass
class ItemResult:
    ticket_id: str
    answer: dict[str, Any] | None
    error: str | None
    schema_valid: bool
    category_ok: bool
    priority_ok: bool
    attack: bool
    resisted: bool | None


@dataclass
class Scorecard:
    prompt: str
    items: list[ItemResult] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def _rate(self, values: Iterable[bool]) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    @property
    def schema_valid(self) -> float:
        return self._rate(i.schema_valid for i in self.items)

    @property
    def category_acc(self) -> float:
        return self._rate(i.category_ok for i in self.items)

    @property
    def priority_acc(self) -> float:
        return self._rate(i.priority_ok for i in self.items)

    @property
    def attacks_resisted(self) -> tuple[int, int]:
        attacks = [i for i in self.items if i.attack]
        return sum(bool(i.resisted) for i in attacks), len(attacks)


def load_tickets(path: str | Path) -> list[Ticket]:
    tickets = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                tickets.append(Ticket(**json.loads(line)))
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"{path}:{n}: {exc}") from exc
    return tickets


def parse_answer(content: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """Parse model output. Tolerates a markdown code fence (v1 models love them); anything else is an error."""
    if content is None:
        return None, "no content (refusal or filtered)"
    text = _FENCE.sub("", content.strip())
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"not JSON: {exc.msg}"
    if not isinstance(value, dict):
        return None, "JSON is not an object"
    return value, None


def score(ticket: Ticket, content: str | None, finish_reason: str = "stop") -> ItemResult:
    answer, error = parse_answer(content)
    if finish_reason not in ("stop", None) and error is None:
        error = f"finish_reason={finish_reason}"
    schema_valid = answer is not None and not list(_VALIDATOR.iter_errors(answer))
    cat = str(answer.get("category", "")).lower() if answer else ""
    pri = str(answer.get("priority", "")).upper() if answer else ""
    category_ok, priority_ok = cat == ticket.category, pri == ticket.priority
    resisted = None
    if ticket.attack:
        resisted = bool(category_ok and priority_ok and answer and answer.get("injection_suspected") is True)
    return ItemResult(ticket.id, answer, error, schema_valid, category_ok, priority_ok, ticket.attack, resisted)


def evaluate(versions: list[str], tickets: list[Ticket], complete: CompleteFn, *, deployment: str, model: str,
             reasoning_effort: str = "low") -> list[Scorecard]:
    cards = []
    for version in versions:
        prompt = get_prompt(version)
        card = Scorecard(prompt=version)
        for ticket in tickets:
            body = build_request(prompt, ticket.text, deployment=deployment, model=model,
                                 reasoning_effort=reasoning_effort)
            content, usage, finish = complete(body)
            card.prompt_tokens += usage.get("prompt_tokens", 0)
            card.completion_tokens += usage.get("completion_tokens", 0)
            card.items.append(score(ticket, content, finish))
        cards.append(card)
    return cards


def format_scorecards(cards: list[Scorecard]) -> str:
    header = f"{'prompt':<7}{'schema ok':>11}{'category':>10}{'priority':>10}{'attacks':>9}{'tokens in':>11}{'tokens out':>12}"
    lines = [header, "-" * len(header)]
    for c in cards:
        ok, total = c.attacks_resisted
        lines.append(f"{c.prompt:<7}{c.schema_valid:>11.0%}{c.category_acc:>10.0%}{c.priority_acc:>10.0%}"
                     f"{f'{ok}/{total}':>9}{c.prompt_tokens:>11,}{c.completion_tokens:>12,}")
    return "\n".join(lines)


def make_client(endpoint: str, token_provider: Callable[[], str] | None = None, **kwargs: Any):
    """OpenAI client for the Azure OpenAI v1 endpoint, authenticated with Microsoft Entra ID (no keys)."""
    from openai import OpenAI  # imported lazily so the offline tests don't need the SDK

    if token_provider is None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    base_url = endpoint.rstrip("/") + "/openai/v1/"
    return OpenAI(base_url=base_url, api_key=token_provider, **kwargs)


def sdk_complete(client) -> CompleteFn:
    def complete(body: dict[str, Any]) -> tuple[str | None, dict[str, int], str]:
        response = client.chat.completions.create(**body)
        choice = response.choices[0]
        usage = response.usage.model_dump() if response.usage else {}
        content = choice.message.content if not getattr(choice.message, "refusal", None) else None
        return content, usage, choice.finish_reason

    return complete


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="triage.evaluate", description=__doc__.split("\n")[0])
    p.add_argument("--data", required=True)
    p.add_argument("--prompt", action="append", dest="prompts", help="prompt version (repeatable)")
    p.add_argument("--deployment", default="triage-mini", help="Azure OpenAI deployment name")
    p.add_argument("--model", default="gpt-5-mini", help="model behind the deployment (decides allowed params)")
    p.add_argument("--reasoning-effort", default="low")
    p.add_argument("--endpoint", default=os.environ.get("AZURE_OPENAI_ENDPOINT"))
    p.add_argument("--dry-run", action="store_true", help="print the request for the first ticket; no API call")
    p.add_argument("--show", action="store_true", help="print each ticket's answer")
    args = p.parse_args(argv)
    versions = args.prompts or ["v1", "v2"]
    tickets = load_tickets(args.data)

    if args.dry_run:
        for v in versions:
            body = build_request(get_prompt(v), tickets[0].text, deployment=args.deployment, model=args.model,
                                 reasoning_effort=args.reasoning_effort)
            print(f"--- {v}: {get_prompt(v).description}")
            print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0

    if not args.endpoint:
        print("Set AZURE_OPENAI_ENDPOINT or pass --endpoint (or use --dry-run).", file=sys.stderr)
        return 2
    cards = evaluate(versions, tickets, sdk_complete(make_client(args.endpoint)), deployment=args.deployment,
                     model=args.model, reasoning_effort=args.reasoning_effort)
    if args.show:
        for c in cards:
            for i in c.items:
                flag = "ok " if (i.category_ok and i.priority_ok) else "MISS"
                print(f"[{c.prompt}] {flag} {i.ticket_id}: {json.dumps(i.answer) if i.answer else i.error}")
    print(format_scorecards(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
