"""Security-trimmed hybrid retrieval from Azure AI Search.

Every query carries   group_ids/any(g: search.in(g, '<caller groups>'))   so a chunk is only a candidate if the
caller is in one of its groups. The filter is built from validated GUIDs only (never from free text), and a
caller with no groups gets no results at all instead of an unfiltered query.
"""
from __future__ import annotations

from dataclasses import dataclass

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery

from .identity import GUID, Caller

SELECT = ["id", "title", "url", "chunk"]   # group_ids is not retrievable, and we don't ask for it


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    chunk: str
    score: float


def security_filter(groups: tuple[str, ...]) -> str:
    if not groups:
        raise ValueError("No groups: refusing to build an unfiltered query.")
    bad = [g for g in groups if not GUID.match(g)]
    if bad:
        raise ValueError(f"Not a group object id: {bad[0]!r}")
    return f"group_ids/any(g: search.in(g, '{','.join(groups)}', ','))"


class Retriever:
    def __init__(self, client: SearchClient, top: int = 5, k_nearest: int = 30, vector_field: str = "content_vector"):
        self.client, self.top, self.k, self.vector_field = client, top, k_nearest, vector_field

    def search(self, question: str, caller: Caller) -> list[Source]:
        if not caller.groups:
            return []
        results = self.client.search(
            search_text=question,
            vector_queries=[VectorizableTextQuery(text=question, k_nearest_neighbors=self.k, fields=self.vector_field)],
            filter=security_filter(caller.groups),
            select=SELECT,
            top=self.top,
        )
        return [Source(r["id"], r["title"], r["url"], r["chunk"], r["@search.score"]) for r in results]
