"""Four ways to retrieve from the same index, so they can be compared on the same questions.

- keyword:          full-text (BM25) on the searchable text fields
- vector:           a text vector query; the index's vectorizer embeds the question in the service
- hybrid:           both in one request; the service fuses the two rankings with RRF
- hybrid_semantic:  hybrid, then the semantic ranker re-ranks the fused results (@search.rerankerScore, 0-4)

Learn: in a hybrid query `top` sets how many results come back; `k` on the vector query is the number of nearest
neighbours fed into the fusion. Semantic ranking runs after RRF.
"""
from __future__ import annotations

from typing import Any

from .hits import Hit
from .index_schema import SEMANTIC_CONFIG, VECTOR_FIELD

MODES = ("keyword", "vector", "hybrid", "hybrid_semantic")
SELECT = ["id", "source", "section_key", "section", "content"]


def query_kwargs(question: str, mode: str, *, top: int = 5, k: int = 50) -> dict[str, Any]:
    from azure.search.documents.models import VectorizableTextQuery

    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    kwargs: dict[str, Any] = {"select": SELECT, "top": top}
    if mode in ("keyword", "hybrid", "hybrid_semantic"):
        kwargs["search_text"] = question
    if mode in ("vector", "hybrid", "hybrid_semantic"):
        kwargs["vector_queries"] = [VectorizableTextQuery(text=question, k_nearest_neighbors=k, fields=VECTOR_FIELD)]
    if mode == "hybrid_semantic":
        kwargs["query_type"] = "semantic"
        kwargs["semantic_configuration_name"] = SEMANTIC_CONFIG
    return kwargs


def search(search_client, question: str, mode: str, *, top: int = 5) -> list[Hit]:
    hits = []
    for doc in search_client.search(**query_kwargs(question, mode, top=top)):
        hits.append(Hit(
            id=doc["id"], section_key=doc["section_key"], source=doc["source"], section=doc["section"],
            content=doc["content"], score=doc.get("@search.score"), reranker_score=doc.get("@search.reranker_score"),
        ))
    return hits


class AzureRetriever:
    """Callable retriever over an Azure AI Search index, keyless by default."""

    def __init__(self, endpoint: str, index_name: str, credential=None, **client_kwargs):
        from azure.search.documents import SearchClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self.client = SearchClient(endpoint, index_name, credential, **client_kwargs)

    def __call__(self, question: str, mode: str, top: int = 5) -> list[Hit]:
        return search(self.client, question, mode, top=top)
