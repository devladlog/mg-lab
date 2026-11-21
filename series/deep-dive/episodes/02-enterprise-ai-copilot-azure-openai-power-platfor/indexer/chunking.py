"""Split Markdown/text into retrieval chunks that keep their heading path ("Leave policy > Carry-over")."""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    title: str        # document title (first H1, else file name)
    heading: str      # heading path of the section
    text: str         # what gets embedded and shown to the model


def chunk_markdown(text: str, fallback_title: str, max_chars: int = 1200, overlap: int = 150) -> list[Chunk]:
    title, path, buf, sections = fallback_title, [], [], []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" > ".join(path) or title, body))
        buf.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        m = _HEADING.match(line)
        if m:
            flush()
            level, name = len(m.group(1)), m.group(2)
            if level == 1 and title == fallback_title:
                title = name
            path[:] = path[: level - 1] + [name]
        else:
            buf.append(line)
    flush()

    chunks = []
    for heading, body in sections:
        for piece in _split(body, max_chars, overlap):
            chunks.append(Chunk(title, heading, f"{heading}\n{piece}"))
    return chunks


def _split(body: str, max_chars: int, overlap: int) -> list[str]:
    if len(body) <= max_chars:
        return [body]
    pieces, start = [], 0
    while start < len(body):
        end = min(len(body), start + max_chars)
        if end < len(body):                       # prefer to cut at a sentence or line end
            cut = max(body.rfind(". ", start, end), body.rfind("\n", start, end))
            if cut > start + max_chars // 2:
                end = cut + 1
        pieces.append(body[start:end].strip())
        if end >= len(body):
            break
        start = max(end - overlap, start + 1)
    return pieces
