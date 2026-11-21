"""Turn the Markdown sources in knowledge/ into real .docx files, one per document.

Markdown subset: '# Title', '## Heading', paragraphs, '- bullets' and pipe tables. The title becomes the Word
"Heading 1" so the subject of the document is in the text, not only in the file name.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from docx import Document

FRONT = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
FIXED_TIME = dt.datetime(2026, 11, 1, 9, 0, 0)  # reproducible files


@dataclass
class Source:
    path: Path
    title: str
    library: str
    body: str
    faq: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def docx_name(self) -> str:
        return self.path.stem + ".docx"


def load_source(path: Path) -> Source:
    text = Path(path).read_text(encoding="utf-8")
    m = FRONT.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing YAML front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    for key in ("title", "library"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: front matter needs '{key}'")
    return Source(Path(path), str(meta["title"]), str(meta["library"]), m.group(2).strip() + "\n",
                  list(meta.get("faq") or []))


def load_sources(folder: Path) -> List[Source]:
    return [load_source(p) for p in sorted(Path(folder).glob("*.md")) if not p.name.startswith("_")]


def _blocks(body: str) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    para: List[str] = []
    table: List[List[str]] = []

    def flush_para():
        if para:
            out.append(("p", " ".join(para)))
            para.clear()

    def flush_table():
        if table:
            out.append(("table", [r for r in table]))
            table.clear()

    for line in body.splitlines():
        s = line.rstrip()
        if s.startswith("|"):
            flush_para()
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            table.append(cells)
            continue
        flush_table()
        if s.startswith("## "):
            flush_para(); out.append(("h2", s[3:].strip()))
        elif s.startswith("# "):
            flush_para(); out.append(("h1", s[2:].strip()))
        elif s.startswith("- "):
            flush_para(); out.append(("li", s[2:].strip()))
        elif s == "":
            flush_para()
        else:
            para.append(s.strip())
    flush_para(); flush_table()
    return out


def build_docx(src: Source, target: Path) -> Path:
    doc = Document()
    for kind, val in _blocks(src.body):
        if kind == "h1":
            doc.add_heading(val, level=1)
        elif kind == "h2":
            doc.add_heading(val, level=2)
        elif kind == "li":
            doc.add_paragraph(val, style="List Bullet")
        elif kind == "p":
            doc.add_paragraph(val)
        elif kind == "table":
            t = doc.add_table(rows=len(val), cols=len(val[0]))
            t.style = "Light Grid Accent 1"
            for i, row in enumerate(val):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
    cp = doc.core_properties
    cp.title = src.title
    cp.author = "Contoso Vendor Management Office"
    cp.created = cp.modified = FIXED_TIME
    cp.last_modified_by = "Contoso Vendor Management Office"
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(target))
    return target


def build_all(sources_dir: Path, out_dir: Path) -> Dict[str, List[Path]]:
    """Writes out_dir/<Library>/<name>.docx and returns {library: [files]}."""
    result: Dict[str, List[Path]] = {}
    for s in load_sources(sources_dir):
        result.setdefault(s.library, []).append(build_docx(s, Path(out_dir) / s.library / s.docx_name))
    return result


def docx_text(path: Path) -> str:
    """All text of a .docx (paragraphs and table cells), for fact checks."""
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)
