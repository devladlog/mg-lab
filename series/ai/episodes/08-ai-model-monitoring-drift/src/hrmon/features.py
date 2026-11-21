"""Input features computed locally from the question, so the question text itself never leaves the app.

The language hint is a deliberately cheap heuristic (Portuguese stopwords and diacritics), not a language service:
good enough to see a population shift, not to label a single message.
"""
from __future__ import annotations

import re

LENGTH_BUCKETS = [(60, "<60"), (120, "60-119"), (200, "120-199")]
PT_WORDS = {"de", "do", "da", "o", "a", "os", "as", "que", "não", "nao", "para", "posso", "como", "meu", "minha",
            "tenho", "quantos", "onde", "quem", "dias", "é", "em", "um", "uma", "no", "na", "com", "preciso"}
EN_WORDS = {"the", "is", "my", "how", "can", "do", "i", "a", "to", "for", "what", "who", "when", "does", "of", "in"}
TOKEN = re.compile(r"[a-záàâãéêíóôõúç]+")


def length_bucket(text: str) -> str:
    n = len(text)
    for limit, label in LENGTH_BUCKETS:
        if n < limit:
            return label
    return "200+"


def language_hint(text: str) -> str:
    words = TOKEN.findall(text.lower())
    pt = sum(w in PT_WORDS for w in words) + 2 * len(re.findall(r"[ãõçáéíóúâê]", text.lower()))
    en = sum(w in EN_WORDS for w in words)
    if pt == en == 0:
        return "other"
    return "pt" if pt > en else "en"


def input_features(question: str) -> dict[str, str]:
    return {"lang": language_hint(question), "length": length_bucket(question)}
