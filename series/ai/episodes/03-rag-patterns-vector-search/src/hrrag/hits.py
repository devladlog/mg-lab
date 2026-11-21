"""The one result shape every retriever returns (Azure AI Search or the local test double)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hit:
    id: str
    section_key: str
    source: str
    section: str
    content: str
    score: float  # @search.score: BM25, cosine-based, or RRF depending on the query
    reranker_score: float | None = None  # @search.rerankerScore (0-4) when the semantic ranker ran
