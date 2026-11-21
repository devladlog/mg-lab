"""Reciprocal Rank Fusion, as Azure AI Search documents it for hybrid queries.

Microsoft Learn ("Relevance scoring in hybrid search using RRF"): each document gets 1/(rank + k) from every ranked
list it appears in, with k a small constant such as 60; the scores are summed and sorted. The k of RRF is
unrelated to the k (nearest neighbours) of a vector query. Semantic ranking, if enabled, runs after RRF.

The search service does this for us. This reference implementation exists so the local test double behaves like
the service, and so the behaviour is visible in a unit test: a document ranked well in *both* lists beats a
document ranked first in only one.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

RRF_K = 60


def rrf(ranked_lists: Iterable[Sequence[str]], k: int = RRF_K, weights: Sequence[float] | None = None) -> list[tuple[str, float]]:
    """Fuse ranked lists of document ids. Ranks start at 1. Optional per-list weights (default 1.0)."""
    lists = list(ranked_lists)
    weights = list(weights) if weights is not None else [1.0] * len(lists)
    if len(weights) != len(lists):
        raise ValueError("one weight per ranked list")
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    order = 0
    for ranked, weight in zip(lists, weights):
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] += weight / (rank + k)
            if doc_id not in first_seen:
                first_seen[doc_id] = order
                order += 1
    # ties: keep first-seen order so results are deterministic
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
