"""An offline, in-memory stand-in for the search index, used by the tests and by `--local` runs.

It is NOT a replacement for Azure AI Search and its "vectors" are NOT semantic: `HashingEmbedder` hashes words and
character trigrams into a fixed-size vector, so it only catches spelling-level similarity ("holiday"/"holidays"),
never meaning ("vacation"/"annual leave"). Real embeddings come from text-embedding-3-small in Azure OpenAI.
What it does reproduce faithfully is the *plumbing*: keyword ranking (BM25), vector ranking (cosine), RRF fusion
of the two and the result shape, so the evaluation harness and the answer pipeline can be tested without a cloud.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from .chunking import Chunk
from .fusion import rrf
from .hits import Hit

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an and are at be can do does for from how i if in is it my of on or the to what when which who with".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class HashingEmbedder:
    """Deterministic feature-hashing embedder (test double). Same input -> same unit-length vector."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        return h % self.dimensions, (1.0 if (h >> 63) & 1 else -1.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dimensions
            for tok in tokenize(text):
                features = [f"w:{tok}"] + [f"c:{tok[i:i + 3]}" for i in range(max(1, len(tok) - 2))]
                for f in features:
                    i, sign = self._bucket(f)
                    v[i] += sign
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both unit length


class LocalIndex:
    """BM25 (k1=1.2, b=0.75) + brute-force cosine + RRF over a list of chunks."""

    def __init__(self, chunks: list[Chunk], embedder: HashingEmbedder | None = None, k1: float = 1.2, b: float = 0.75):
        self.chunks = {c.id: c for c in chunks}
        self.embedder = embedder or HashingEmbedder()
        self.k1, self.b = k1, b
        self.tf = {c.id: Counter(tokenize(c.content)) for c in chunks}
        self.length = {cid: sum(tf.values()) for cid, tf in self.tf.items()}
        self.avg_len = sum(self.length.values()) / max(1, len(self.length))
        df = Counter(t for tf in self.tf.values() for t in tf)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.vectors = dict(zip(self.chunks, self.embedder.embed([c.content for c in chunks])))

    def bm25(self, query: str, top: int = 50) -> list[tuple[str, float]]:
        terms = tokenize(query)
        scores = {}
        for cid, tf in self.tf.items():
            s = 0.0
            for t in terms:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.length[cid] / self.avg_len))
            if s > 0:
                scores[cid] = s
        return sorted(scores.items(), key=lambda kv: -kv[1])[:top]

    def knn(self, query: str, k: int = 50) -> list[tuple[str, float]]:
        q = self.embedder.embed([query])[0]
        return sorted(((cid, cosine(q, v)) for cid, v in self.vectors.items()), key=lambda kv: -kv[1])[:k]

    def search(self, query: str, mode: str, top: int = 5) -> list[Hit]:
        if mode == "keyword":
            ranked = self.bm25(query)
        elif mode == "vector":
            ranked = self.knn(query)
        elif mode in ("hybrid", "hybrid_semantic"):
            # No local semantic ranker exists; hybrid_semantic falls back to plain hybrid here.
            ranked = rrf([[cid for cid, _ in self.bm25(query)], [cid for cid, _ in self.knn(query)]])
        else:
            raise ValueError(f"unknown mode {mode!r}")
        hits = []
        for cid, score in ranked[:top]:
            c = self.chunks[cid]
            hits.append(Hit(cid, c.section_key, c.source, c.section, c.content, score))
        return hits
