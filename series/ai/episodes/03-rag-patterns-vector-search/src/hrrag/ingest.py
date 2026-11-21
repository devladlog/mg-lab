"""Create the index and push the chunked, embedded handbook into it (push model, keyless).

    PYTHONPATH=src python -m hrrag.ingest --search-endpoint https://<search>.search.windows.net \
        --aoai-endpoint https://<aoai>.openai.azure.com --embedding-deployment embed-small

Learn ("Index large data sets", "Service limits"): one indexing request carries at most 1,000 documents and 16 MB.
Each document in a batch succeeds or fails on its own, so the per-document results must be checked.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterator, Sequence

from .chunking import Chunk, chunk_folder
from .index_schema import EMBEDDING_DIMENSIONS, INDEX_NAME, VECTOR_FIELD, build_index

MAX_BATCH = 1000


def to_documents(chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> list[dict[str, Any]]:
    if len(chunks) != len(vectors):
        raise ValueError("one vector per chunk")
    return [
        {"id": c.id, "source": c.source, "section_key": c.section_key, "title": c.title, "section": c.section,
         "content": c.content, VECTOR_FIELD: list(v)}
        for c, v in zip(chunks, vectors)
    ]


def batches(items: Sequence[Any], size: int = MAX_BATCH) -> Iterator[Sequence[Any]]:
    if not 1 <= size <= MAX_BATCH:
        raise ValueError(f"batch size must be between 1 and {MAX_BATCH}")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def upload(search_client, documents: Sequence[dict[str, Any]], batch_size: int = 100) -> int:
    """merge_or_upload in batches; raise with the failing keys if any document was rejected."""
    ok, failed = 0, []
    for batch in batches(documents, batch_size):
        for result in search_client.merge_or_upload_documents(documents=list(batch)):
            if result.succeeded:
                ok += 1
            else:
                failed.append(f"{result.key}: {result.status_code} {result.error_message}")
    if failed:
        raise RuntimeError("documents rejected by the index:\n  " + "\n  ".join(failed))
    return ok


def run(search_endpoint: str, aoai_endpoint: str, embedding_deployment: str, data: str | Path, *,
        index_name: str = INDEX_NAME, credential=None, aoai_client=None) -> int:
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient

    from .embeddings import embed_texts, make_aoai_client

    if credential is None:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
    index = build_index(aoai_endpoint, embedding_deployment, name=index_name)
    SearchIndexClient(search_endpoint, credential).create_or_update_index(index)
    chunks = chunk_folder(data)
    client = aoai_client or make_aoai_client(aoai_endpoint)
    vectors = embed_texts(client, embedding_deployment, [c.content for c in chunks], dimensions=EMBEDDING_DIMENSIONS)
    return upload(SearchClient(search_endpoint, index_name, credential), to_documents(chunks, vectors))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hrrag.ingest", description="Create the index and upload the handbook chunks.")
    p.add_argument("--search-endpoint", required=True)
    p.add_argument("--aoai-endpoint", required=True)
    p.add_argument("--embedding-deployment", default="embed-small")
    p.add_argument("--index", default=INDEX_NAME)
    p.add_argument("--data", default="data/handbook")
    p.add_argument("--dry-run", action="store_true", help="only chunk and print, no Azure calls")
    a = p.parse_args(argv)
    if a.dry_run:
        chunks = chunk_folder(a.data)
        for c in chunks:
            print(f"{c.id:45} {len(c.content):5} chars")
        print(f"{len(chunks)} chunks from {len({c.source for c in chunks})} documents")
        return 0
    n = run(a.search_endpoint, a.aoai_endpoint, a.embedding_deployment, a.data, index_name=a.index)
    print(f"indexed {n} chunks into '{a.index}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
