"""Labelled HR messages -> train / validation / test, and the chat-format JSONL that fine-tuning expects."""
from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .labels import CATEGORIES, Label


@dataclass(frozen=True)
class Example:
    id: str
    text: str
    category: str
    urgency: str | None = None        # None: the golden set from episode 8 only carries the category
    needs_human: bool | None = None

    @property
    def label(self) -> Label | None:
        if self.urgency is None or self.needs_human is None:
            return None
        return Label(self.category, self.urgency, self.needs_human)

    @property
    def lang(self) -> str:
        return guess_lang(self.text)


_PT_WORDS = {"o", "a", "os", "as", "de", "da", "do", "para", "que", "não", "meu", "minha", "como", "posso", "um",
             "uma", "em", "com", "é", "foi", "há", "tenho", "preciso", "quais", "quando", "onde", "qual", "por",
             "se", "no", "na", "dos", "das", "mais", "já", "ao", "me", "fui", "recebi", "quero", "sinto", "perdi"}


def guess_lang(text: str) -> str:
    """Tiny heuristic (diacritics + common Portuguese words) used only to report the language mix."""
    words = re.findall(r"[\wÀ-ÿ]+", text.lower())
    pt = sum(w in _PT_WORDS for w in words)
    if re.search(r"[ãõçáéíóúâêô]", text.lower()):
        pt += 2
    return "pt" if pt >= 2 else "en"


def load_labelled(path: str | Path) -> list[Example]:
    out = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Example(d["id"], d["text"], d["category"], d["urgency"], bool(d["needs_human"])))
    return out


def load_golden(path: str | Path) -> list[Example]:
    """Episode 8's golden set: question + category only. Kept out of training and used as extra test data."""
    out = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Example(d["id"], d["question"], d["category"]))
    return out


@dataclass
class Splits:
    train: list[Example]
    validation: list[Example]
    test: list[Example]


def split(examples: list[Example], seed: int = 7, val_frac: float = 0.13, test_frac: float = 0.20) -> Splits:
    """Stratified by category, deterministic for a given seed. Test is never uploaded."""
    by_cat: dict[str, list[Example]] = defaultdict(list)
    for e in examples:
        by_cat[e.category].append(e)
    rng = random.Random(seed)
    train, val, test = [], [], []
    for cat in CATEGORIES:
        items = sorted(by_cat.get(cat, []), key=lambda e: e.id)
        rng.shuffle(items)
        n_test, n_val = round(len(items) * test_frac), round(len(items) * val_frac)
        test += items[:n_test]
        val += items[n_test:n_test + n_val]
        train += items[n_test + n_val:]
    return Splits(sorted(train, key=lambda e: e.id), sorted(val, key=lambda e: e.id), sorted(test, key=lambda e: e.id))


def to_chat(e: Example, system: str) -> dict:
    """One training example: system + user message + the exact answer we want."""
    if e.label is None:
        raise ValueError(f"{e.id} has no full label; it can't be a training example")
    return {"messages": [{"role": "system", "content": system},
                         {"role": "user", "content": e.text},
                         {"role": "assistant", "content": e.label.to_json()}]}


def write_jsonl(path: str | Path, rows: list[dict], bom: bool = True) -> None:
    """Learn: training and validation files are UTF-8 JSON Lines. The how-to also states they include a
    byte-order mark, so we write one (utf-8-sig); readers here accept both."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8-sig").splitlines() if l.strip()]
