"""Token counting for training files. Learn: estimate with the tokenizer of the model you fine-tune. gpt-4.1 models
use o200k_base; if tiktoken can't load it (offline), fall back to characters / 4 and say so."""
from __future__ import annotations

from functools import lru_cache

PER_MESSAGE_OVERHEAD = 3   # rough chat-framing allowance per message; the service's own count is authoritative


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base")
    except Exception:       # offline / vocabulary not cached
        return None


def exact() -> bool:
    return _encoder() is not None


def count_text(text: str) -> int:
    enc = _encoder()
    return len(enc.encode(text)) if enc else max(1, len(text) // 4)


def count_example(row: dict) -> int:
    return sum(count_text(m["content"]) + PER_MESSAGE_OVERHEAD for m in row["messages"])


def count_rows(rows: list[dict]) -> int:
    return sum(count_example(r) for r in rows)
