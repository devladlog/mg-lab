"""Service limits from Learn ("Service limits for Azure Language", preconfigured features) and the helpers that respect them.

Learn measures a document in text elements (StringInfo.LengthInTextElements). We count Python code points, which are
never fewer than text elements, so a chunk that fits by our count also fits by the service's count.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")

MAX_CHARS = 5120                       # synchronous call, per document
MAX_DOCS = {"language": 1000, "sentiment": 10, "key_phrases": 10, "entities": 5, "pii": 5}   # documents per request
RECORD_CHARS = 1000                    # pricing: "a text record is measured as 1000 characters"
F0_FREE_RECORDS_PER_MONTH = 5000       # Learn: the free tier covers 5,000 text records per month

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def text_records(text: str) -> int:
    return max(1, math.ceil(len(text) / RECORD_CHARS)) if text else 0


def batched(items: Sequence[T], size: int) -> Iterator[list[T]]:
    for i in range(0, len(items), size):
        yield list(items[i:i + size])


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split on paragraph, then sentence, then (last resort) hard cut, so that every chunk is <= limit characters."""
    chunks: list[str] = []
    cur = ""

    def flush():
        nonlocal cur
        if cur.strip():
            chunks.append(cur.strip())
        cur = ""

    def pieces(par: str) -> Iterable[str]:
        if len(par) <= limit:
            yield par
            return
        for sent in _SENTENCE.split(par):
            if len(sent) <= limit:
                yield sent
            else:
                for i in range(0, len(sent), limit):
                    yield sent[i:i + limit]

    for par in re.split(r"\n\s*\n", text):
        for piece in pieces(par):
            joiner = "\n\n" if cur else ""
            if len(cur) + len(joiner) + len(piece) > limit:
                flush()
                joiner = ""
            cur += joiner + piece
    flush()
    return chunks
