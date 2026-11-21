"""Turn SharePoint files into index documents (with group_ids) and push them to Azure AI Search."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Callable, Iterable

from chunking import chunk_markdown
from graph_source import TEXT_EXTENSIONS, DriveFile

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
INDEX_FILE = Path(__file__).resolve().parents[1] / "index" / "policies-index.json"


def doc_key(f: DriveFile, n: int) -> str:
    """Keys allow letters, digits, '_', '-', '='. URL-safe base64 of drive+item keeps any id valid and stable."""
    raw = f"{f.drive_id}|{f.item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode() + f"_{n}"


def build_documents(f: DriveFile, content: bytes, groups: list[str],
                    embed: Callable[[list[str]], list[list[float]]]) -> list[dict]:
    if not groups:
        raise ValueError(f"{f.path}: no groups configured. A document nobody is allowed to read is never indexed "
                         "open to everyone.")
    bad = [g for g in groups if not GUID.match(g)]
    if bad:
        raise ValueError(f"{f.path}: '{bad[0]}' is not an Entra group object id")
    if not f.name.lower().endswith(TEXT_EXTENSIONS):
        return []   # Office/PDF need text extraction first (e.g. Document Intelligence layout); skipped here
    text = content.decode("utf-8-sig")
    chunks = chunk_markdown(text, fallback_title=Path(f.name).stem)
    vectors = embed([c.text for c in chunks]) if chunks else []
    return [{
        "@search.action": "mergeOrUpload",
        "id": doc_key(f, i),
        "title": c.title,
        "url": f.web_url,
        "chunk": c.text,
        "content_vector": v,
        "group_ids": sorted(g.lower() for g in groups),
        "source_item": f"{f.drive_id}|{f.item_id}",
        "source_modified": f.modified,
    } for i, (c, v) in enumerate(zip(chunks, vectors))]


def make_embedder(client, deployment: str = "embed", batch: int = 16) -> Callable[[list[str]], list[list[float]]]:
    """OpenAI client (Azure OpenAI v1 endpoint) -> function that embeds a list of texts in batches."""
    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch):
            resp = client.embeddings.create(model=deployment, input=texts[i:i + batch])
            out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return out
    return embed


def upload(search_client, docs: Iterable[dict], batch: int = 100) -> int:
    docs, total = list(docs), 0
    for i in range(0, len(docs), batch):
        results = search_client.merge_or_upload_documents(documents=docs[i:i + batch])
        failed = [r.key for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"{len(failed)} documents failed, first: {failed[0]}")
        total += len(results)
    return total


def index_definition(openai_endpoint: str, path: Path = INDEX_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8").replace("${OPENAI_ENDPOINT}", openai_endpoint.rstrip("/")))
