"""Pre-flight checks for a fine-tuning dataset. Everything here runs locally, before a single byte is uploaded.

Sources: the Learn fine-tuning how-to (JSONL chat format, at least 10 examples, 50 is a sensible start, same system
message at inference, keep validation and test data out of training) and the fine-tuning overview's "challenges"
table (duplicates, sensitive information, evaluation leakage)."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import tokens
from .labels import CATEGORIES, parse_label

MIN_EXAMPLES = 10           # Learn: jobs won't proceed with fewer
RECOMMENDED_START = 50      # Learn: "start with 50 well-crafted training data"
MAX_EXAMPLE_TOKENS = 65_536  # Learn: training example context length for gpt-4.1-mini
NEAR_DUPLICATE = 0.8         # Jaccard similarity of word sets
MIN_PER_CLASS = 5

PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+\d{2,3}[ -]?)?(?:9\d{2}|2\d{2})[ -]?\d{3}[ -]?\d{3}(?!\d)"),
    "nif_or_long_number": re.compile(r"(?<!\d)\d{9,}(?!\d)"),
    "card_number": re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
}


@dataclass
class Issue:
    severity: str            # "error" blocks the upload, "warning" doesn't
    code: str
    message: str
    where: str = ""


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity, code, message, where=""):
        self.issues.append(Issue(severity, code, message, where))

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def jaccard(a: str, b: str) -> float:
    A, B = set(normalise(a).split()), set(normalise(b).split())
    return len(A & B) / len(A | B) if A and B else 0.0


def user_text(row: dict) -> str:
    return next((m["content"] for m in row["messages"] if m["role"] == "user"), "")


def check_rows(rows: list[dict], name: str = "training") -> Report:
    """name "validation" skips the size and class-balance advice, which is about the training set."""
    r = Report()
    training = name == "training"
    if len(rows) < MIN_EXAMPLES:
        r.add("error", "too-few", f"{name}: {len(rows)} examples; fine-tuning needs at least {MIN_EXAMPLES}")
    elif training and len(rows) < RECOMMENDED_START:
        r.add("warning", "few", f"{name}: {len(rows)} examples; Learn suggests starting with about {RECOMMENDED_START}")

    systems, seen, labels_by_text, cats = set(), {}, defaultdict(set), Counter()
    for i, row in enumerate(rows, 1):
        where = f"{name}#{i}"
        msgs = row.get("messages")
        if not isinstance(msgs, list) or not msgs:
            r.add("error", "no-messages", "row has no messages list", where)
            continue
        roles = [m.get("role") for m in msgs]
        if roles != ["system", "user", "assistant"]:
            r.add("error", "bad-roles", f"expected system, user, assistant; got {roles}", where)
            continue
        if any(not isinstance(m.get("content"), str) or not m["content"].strip() for m in msgs):
            r.add("error", "empty-content", "a message has empty content", where)
            continue
        systems.add(msgs[0]["content"])
        label = parse_label(msgs[2]["content"])
        if label is None:
            r.add("error", "bad-answer", f"assistant answer is not a valid triage JSON: {msgs[2]['content'][:60]!r}", where)
        else:
            cats[label.category] += 1
            labels_by_text[normalise(msgs[1]["content"])].add(label.to_json())
        if tokens.count_example(row) > MAX_EXAMPLE_TOKENS:
            r.add("error", "too-long", f"example over {MAX_EXAMPLE_TOKENS} tokens", where)
        key = normalise(msgs[1]["content"])
        if key in seen:
            r.add("warning", "duplicate", f"same message as {seen[key]}", where)
        seen.setdefault(key, where)
        blob = " ".join(m["content"] for m in msgs[1:])
        for pii, rx in PII_PATTERNS.items():
            if rx.search(blob):
                r.add("error", "pii", f"looks like personal data ({pii}); remove or mask it before training", where)

    if len(systems) > 1:
        r.add("error", "system-mismatch",
              f"{len(systems)} different system messages; the same one must be used at inference, so use one")
    for text, labs in labels_by_text.items():
        if len(labs) > 1:
            r.add("error", "conflicting-labels", f"same message labelled differently: {text[:50]!r}")
    if training:
        for c in sorted(set(CATEGORIES) - set(cats)):
            r.add("warning", "thin-class", f"{name}: no examples of category '{c}'")
        for c, n in cats.items():
            if n < MIN_PER_CLASS:
                r.add("warning", "thin-class", f"{name}: only {n} examples of category '{c}'")
    return r


def check_leakage(train_rows: list[dict], held_out: dict[str, list[str]]) -> Report:
    """held_out: set name -> texts that must never be trained on (validation, test, the episode 8 golden set)."""
    r = Report()
    for row_i, row in enumerate(train_rows, 1):
        t = user_text(row)
        for set_name, texts in held_out.items():
            for h in texts:
                if normalise(t) == normalise(h):
                    r.add("error", "leak-exact", f"training example is also in {set_name}: {t[:50]!r}", f"train#{row_i}")
                elif jaccard(t, h) >= NEAR_DUPLICATE:
                    r.add("error", "leak-near", f"training example is a near copy of one in {set_name}: {t[:50]!r}",
                          f"train#{row_i}")
    return r


def check_file_encoding(path: str | Path) -> Report:
    """UTF-8 without a stray replacement character; BOM present (Learn says the files include one)."""
    r = Report()
    raw = Path(path).read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        r.add("warning", "no-bom", f"{Path(path).name}: no UTF-8 byte-order mark; the Learn how-to says files include one")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        r.add("error", "not-utf8", f"{Path(path).name}: not valid UTF-8 ({e})")
    for n, line in enumerate(raw.decode("utf-8-sig", errors="replace").splitlines(), 1):
        try:
            json.loads(line)
        except json.JSONDecodeError:
            r.add("error", "bad-json", f"{Path(path).name} line {n} is not valid JSON")
    if len(raw) >= 512 * 1024 * 1024:
        r.add("error", "too-big", "file is 512 MB or more; Learn: it must be smaller than 512 MB")
    return r


def merge(*reports: Report) -> Report:
    out = Report()
    for rep in reports:
        out.issues.extend(rep.issues)
    return out
