"""ask(): retrieve (trimmed) -> ground -> generate -> check. No sources means no model call."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from openai import OpenAI

from .grounding import NO_ANSWER, build_messages, check_citations
from .identity import Caller
from .retrieval import Retriever

FILTERED = "The answer was blocked by the content filter."
DEFAULT_SCOPE = "https://ai.azure.com/.default"   # Learn: the Entra scope for Azure OpenAI endpoints


def make_openai(endpoint: str, credential=None, scope: str = DEFAULT_SCOPE) -> OpenAI:
    """Azure OpenAI v1 endpoint, keyless: the token provider is passed as api_key (the SDK calls it per request)."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    token_provider = get_bearer_token_provider(credential or DefaultAzureCredential(), scope)
    return OpenAI(base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=token_provider)


@dataclass
class Answer:
    answer: str
    citations: list[dict]
    grounded: bool
    sources_considered: int
    usage: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def ask(question: str, caller: Caller, retriever: Retriever, llm: OpenAI, deployment: str | None = None,
        max_tokens: int = 600) -> Answer:
    question = (question or "").strip()
    if not question:
        raise ValueError("Empty question.")
    if len(question) > 1000:
        raise ValueError("Question is longer than 1000 characters.")

    sources = retriever.search(question, caller)
    if not sources:
        # Nothing this caller may read matches: don't spend tokens, don't let the model improvise.
        return Answer(NO_ANSWER, [], grounded=True, sources_considered=0)

    resp = llm.chat.completions.create(
        model=deployment or os.environ.get("CHAT_DEPLOYMENT", "chat"),
        messages=build_messages(question, sources),
        max_completion_tokens=max_tokens,
    )
    usage = resp.usage.model_dump(include={"prompt_tokens", "completion_tokens", "total_tokens"}) if resp.usage else None
    choice = resp.choices[0]
    if choice.finish_reason == "content_filter":      # the completion itself was filtered (HTTP 200)
        return Answer(FILTERED, [], grounded=False, sources_considered=len(sources), usage=usage)
    checked = check_citations(choice.message.content, sources)
    return Answer(checked.answer, checked.citations, checked.grounded, len(sources), usage)
