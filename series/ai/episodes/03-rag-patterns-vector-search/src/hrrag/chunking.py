"""Heading-aware chunking for Markdown documents.

Microsoft Learn ("Chunk large documents for RAG and vector search"):
- Markdown heading syntax can be used to chunk content by sections (variable-sized chunks).
- For fixed-size splitting, start at 512 tokens (about 2,000 characters) with a 25% overlap.
- Appending the document title to chunks from the middle of a document prevents context loss.

So: one chunk per section; a section longer than `max_chars` is split on paragraph/sentence boundaries with
`overlap` characters repeated at the start of the next piece; every chunk carries "Document > Section" in front of
its text, so the chunk still makes sense on its own (for the embedding model, for BM25 and for the LLM).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHARS = 2000  # ~512 tokens
OVERLAP = 500  # 25%

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: str  # valid search document key: letters, digits, '-', '_', '='
    source: str  # file stem, e.g. "leave"
    title: str  # document title (H1)
    section: str  # section heading (H2), or the title for the preamble
    section_key: str  # "leave#carry-over" - what the evaluation set refers to
    content: str  # "Leave policy > Carry-over\n\n<section text>"
    part: int = 0
    meta: dict = field(default_factory=dict, compare=False)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (title, [(section heading, body)]). Text before the first H2 becomes a section named after the title."""
    markdown = _COMMENT.sub("", markdown)  # boilerplate in HTML comments is never indexed
    title, current, body, sections = "", None, [], []
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1 and not title:
            title = m.group(2)
            continue
        if m and len(m.group(1)) == 2:
            if body and "".join(body).strip():
                sections.append((current or title, "\n".join(body).strip()))
            current, body = m.group(2), []
            continue
        body.append(line)
    if body and "".join(body).strip():
        sections.append((current or title, "\n".join(body).strip()))
    return title, sections


def split_long(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    """Split on paragraph, then sentence boundaries; repeat up to `overlap` trailing characters in the next piece."""
    if overlap * 2 >= max_chars:
        raise ValueError("overlap must be less than half of max_chars")  # same rule as the Text Split skill
    if len(text) <= max_chars:
        return [text]
    units = [s for p in re.split(r"\n\s*\n", text) for s in _SENTENCE_END.split(p.strip()) if s]
    pieces, current = [], ""
    for unit in units:
        if len(unit) > max_chars:  # a single monster sentence: hard cut
            unit_parts = [unit[i:i + max_chars] for i in range(0, len(unit), max_chars - overlap)]
        else:
            unit_parts = [unit]
        for u in unit_parts:
            candidate = f"{current} {u}".strip()
            if len(candidate) <= max_chars:
                current = candidate
                continue
            pieces.append(current)
            tail = current[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail  # don't start mid-word
            current = f"{tail} {u}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(markdown: str, source: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[Chunk]:
    title, sections = split_sections(markdown)
    chunks: list[Chunk] = []
    for heading, body in sections:
        prefix = f"{title} > {heading}" if heading != title else title
        budget = max_chars - len(prefix) - 2
        for part, piece in enumerate(split_long(body, budget, min(overlap, budget // 2 - 1))):
            key = f"{source}#{slugify(heading)}"
            chunks.append(Chunk(
                id=f"{slugify(source)}-{slugify(heading)}-{part}",
                source=source, title=title, section=heading, section_key=key,
                content=f"{prefix}\n\n{piece}", part=part,
            ))
    return chunks


def chunk_folder(folder: str | Path, **kwargs) -> list[Chunk]:
    out: list[Chunk] = []
    for path in sorted(Path(folder).glob("*.md")):
        out.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.stem, **kwargs))
    ids = [c.id for c in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk ids: section headings must be unique per document")
    return out
