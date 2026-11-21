"""Token counting with tiktoken (offline). Learn's own token-counting example uses the same library; the encoding
that matches a model is tiktoken's mapping, the billed number is always `usage.prompt_tokens` from the service."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import tiktoken

ENCODINGS = ("cl100k_base", "o200k_base")


@lru_cache(maxsize=None)
def get_encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def encoding_name_for(model: str) -> str:
    try:
        return tiktoken.encoding_for_model(model).name
    except KeyError:
        return "o200k_base"


def count(text: str, encoding: str = "o200k_base") -> int:
    return len(get_encoding(encoding).encode(text))


def pieces(text: str, encoding: str = "o200k_base") -> list[str]:
    """The text as the model sees it: one string per token (bytes decoded leniently)."""
    enc = get_encoding(encoding)
    return [enc.decode_single_token_bytes(t).decode("utf-8", errors="replace") for t in enc.encode(text)]


def load_pairs(path: str | Path) -> list[dict]:
    pairs = json.loads(Path(path).read_text(encoding="utf-8"))
    for p in pairs:
        if not {"id", "en", "pt"} <= p.keys():
            raise ValueError(f"pair {p!r} needs id, en and pt")
    return pairs


def compare(pairs: list[dict], encodings=ENCODINGS) -> list[dict]:
    """Token counts of the same sentence in English and Portuguese, per encoding."""
    rows = []
    for p in pairs:
        row = {"id": p["id"], "en_chars": len(p["en"]), "pt_chars": len(p["pt"])}
        for e in encodings:
            en, pt = count(p["en"], e), count(p["pt"], e)
            row[e] = {"en": en, "pt": pt, "ratio": round(pt / en, 2)}
        rows.append(row)
    return rows


def totals(rows: list[dict], encodings=ENCODINGS) -> dict:
    out = {}
    for e in encodings:
        en, pt = sum(r[e]["en"] for r in rows), sum(r[e]["pt"] for r in rows)
        out[e] = {"en": en, "pt": pt, "ratio": round(pt / en, 2)}
    return out


def render(rows: list[dict], encodings=ENCODINGS) -> str:
    head = f"{'sentence':<9}" + "".join(f"{e + ' en/pt':>22}{'pt/en':>8}" for e in encodings)
    lines = [head]
    for r in rows:
        lines.append(f"{r['id']:<9}" + "".join(f"{r[e]['en']:>13}/{r[e]['pt']:<8}{r[e]['ratio']:>8.2f}" for e in encodings))
    t = totals(rows, encodings)
    lines.append(f"{'total':<9}" + "".join(f"{t[e]['en']:>13}/{t[e]['pt']:<8}{t[e]['ratio']:>8.2f}" for e in encodings))
    return "\n".join(lines)
