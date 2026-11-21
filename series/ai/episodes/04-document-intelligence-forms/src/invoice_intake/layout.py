"""Scanned policy page -> Markdown with the layout model -> section chunks for the episode 3 search index.

    PYTHONPATH=src python -m invoice_intake.layout samples/contoso-expenses-policy.png \
        --endpoint https://<resource>.cognitiveservices.azure.com

Learn ("RAG with Document Intelligence"): the layout model can return the document as Markdown
(outputContentFormat=markdown) with headings, paragraphs and tables preserved, which is the building block for
semantic chunking on section boundaries. Episode 3's chunker splits on '#'/'##'; this module produces exactly that
shape (title + sections) from any scan, PDF or Office file the layout model accepts.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FIGURE_OR_COMMENT = re.compile(r"<!--.*?-->|<figure>.*?</figure>", re.S)


def analyze_markdown(client, path: str | Path, polling_interval: float | None = None) -> str:
    kwargs = {"output_content_format": "markdown"}
    if polling_interval is not None:
        kwargs["polling_interval"] = polling_interval
    with open(path, "rb") as f:
        result = client.begin_analyze_document("prebuilt-layout", f, **kwargs).result()
    return result["content"]


def markdown_sections(markdown: str) -> list[tuple[str, str]]:
    """[(heading path, body)] split on any heading level; page markers and figures dropped."""
    markdown = _FIGURE_OR_COMMENT.sub("", markdown)
    path: list[str] = []
    out, body, current = [], [], None
    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m:
            if current is not None and "\n".join(body).strip():
                out.append((current, "\n".join(body).strip()))
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2)]
            current, body = " > ".join(path), []
        else:
            body.append(line)
    if current is not None and "\n".join(body).strip():
        out.append((current, "\n".join(body).strip()))
    return out


def main(argv: list[str] | None = None) -> int:
    from .process import make_client

    ap = argparse.ArgumentParser(prog="invoice_intake.layout", description="Document -> Markdown -> sections.")
    ap.add_argument("file")
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--save", help="write the Markdown here (e.g. into episode 3's data/handbook/)")
    a = ap.parse_args(argv)
    md = analyze_markdown(make_client(a.endpoint), a.file)
    print(md, "\n" + "=" * 60)
    for heading, body in markdown_sections(md):
        print(f"[{heading}] {len(body)} chars")
    if a.save:
        Path(a.save).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
