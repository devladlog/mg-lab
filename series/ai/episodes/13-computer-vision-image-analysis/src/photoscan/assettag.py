"""Read the Contoso asset tag (CON-12345) out of the OCR lines. The service returns text, never meaning: the pattern,
the confidence floor and the look-alike rule below are ours."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .model import Line

TAG = re.compile(r"\bCON[-\s]?([0-9OoIlSB]{5})\b")      # digits, plus the letters OCR confuses with them
CONFUSED = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"})
MIN_WORD_CONFIDENCE = 0.80


@dataclass
class TagRead:
    tag: str                  # normalised, CON-12345
    raw: str                  # as printed
    confidence: float         # lowest word confidence on that line
    corrected: bool           # look-alike letters were replaced by digits


def find_tags(lines: list[Line]) -> list[TagRead]:
    found: dict[str, TagRead] = {}
    for ln in lines:
        m = TAG.search(ln.text)
        if not m:
            continue
        digits = m.group(1)
        fixed = digits.translate(CONFUSED)
        if not fixed.isdigit():
            continue
        printed = m.group(0)
        words = [w for w in ln.words if w.text and (w.text in printed or printed in w.text)]
        conf = min((w.confidence for w in words), default=min((w.confidence for w in ln.words), default=0.0))
        tag = f"CON-{fixed}"
        read = TagRead(tag, m.group(0), conf, fixed != digits)
        if tag not in found or conf > found[tag].confidence:
            found[tag] = read
    return list(found.values())


def usable(t: TagRead) -> bool:
    return t.confidence >= MIN_WORD_CONFIDENCE and not t.corrected
