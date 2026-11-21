"""Embeddings for indexing, from an Azure OpenAI text-embedding-3-small deployment, keyless.

Same client pattern as episode 1: the OpenAI SDK on the Azure OpenAI v1 endpoint with a Microsoft Entra token
provider (no API keys). Learn: text-embedding-3-small accepts up to 8,191 input tokens per input, so chunks of
about 512 tokens are far below the limit.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence


def make_aoai_client(endpoint: str, token_provider: Callable[[], str] | None = None, **kwargs: Any):
    from openai import OpenAI

    if token_provider is None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    return OpenAI(base_url=endpoint.rstrip("/") + "/openai/v1/", api_key=token_provider, **kwargs)


def embed_texts(client, deployment: str, texts: Sequence[str], *, dimensions: int | None = None,
                batch_size: int = 16) -> list[list[float]]:
    """Embed in small batches (one request per batch); fail loudly if a vector is missing or the size is wrong."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = list(texts[start:start + batch_size])
        kwargs: dict[str, Any] = {"model": deployment, "input": batch}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions
        response = client.embeddings.create(**kwargs)
        data = sorted(response.data, key=lambda d: d.index)
        if len(data) != len(batch):
            raise RuntimeError(f"asked for {len(batch)} embeddings, got {len(data)}")
        vectors.extend(list(d.embedding) for d in data)
    if dimensions is not None and any(len(v) != dimensions for v in vectors):
        raise RuntimeError("embedding size doesn't match the vector field dimensions")
    return vectors
