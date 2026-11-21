"""Will it fit? Weights (file size on disk) + KV cache (computed from the model's architecture) against free VRAM.

This is an ESTIMATE for planning. The truth is `ollama ps` / GET /api/ps after the model is loaded
(size vs size_vram); `bench` prints that. Assumptions are listed in the README.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

GIB = 1024 ** 3
# Ollama FAQ (OLLAMA_KV_CACHE_TYPE): f16 default; q8_0 "about half the memory of f16"; q4_0 "about a quarter".
KV_FACTOR = {"f16": 1.0, "q8_0": 0.5, "q4_0": 0.25}
F16_BYTES = 2
DEFAULT_MARGIN_GIB = 1.0   # our own safety margin for compute buffers and the desktop; NOT from any documentation


@dataclass
class ModelArch:
    arch: str
    layers: int
    heads: int
    kv_heads: int
    embedding: int
    max_context: int

    @property
    def head_dim(self) -> int:
        return self.embedding // self.heads

    @classmethod
    def from_show(cls, show: dict) -> "ModelArch":
        """Read model_info of POST /api/show: <arch>.block_count, .attention.head_count(_kv), .embedding_length, .context_length."""
        info = show.get("model_info") or {}
        arch = info.get("general.architecture")
        if not arch:
            raise ValueError("model_info has no general.architecture")

        def need(key: str):
            if f"{arch}.{key}" not in info:
                raise ValueError(f"model_info has no {arch}.{key}")
            return info[f"{arch}.{key}"]

        def scalar(v) -> int:   # some models store a per-layer list
            return int(round(sum(v) / len(v))) if isinstance(v, list) else int(v)

        heads = scalar(need("attention.head_count"))
        kv = info.get(f"{arch}.attention.head_count_kv")
        return cls(arch=arch, layers=scalar(need("block_count")), heads=heads,
                   kv_heads=scalar(kv) if kv is not None else heads, embedding=scalar(need("embedding_length")),
                   max_context=scalar(need("context_length")))


def kv_cache_bytes(a: ModelArch, context: int, kv_type: str = "f16") -> int:
    """2 (K and V) x layers x kv_heads x head_dim x context x 2 bytes (f16), scaled by the cache type."""
    if kv_type not in KV_FACTOR:
        raise ValueError(f"kv_type must be one of {sorted(KV_FACTOR)}")
    return int(2 * a.layers * a.kv_heads * a.head_dim * context * F16_BYTES * KV_FACTOR[kv_type])


@dataclass
class Fit:
    weights: int
    kv: int
    margin: int
    vram: int
    context: int
    kv_type: str

    @property
    def total(self) -> int:
        return self.weights + self.kv + self.margin

    @property
    def fits(self) -> bool:
        return self.total <= self.vram

    def line(self) -> str:
        g = lambda n: f"{n / GIB:5.1f}"  # noqa: E731
        return (f"weights {g(self.weights)} + KV cache {g(self.kv)} ({self.kv_type}, {self.context} tokens) + margin "
                f"{g(self.margin)} = {g(self.total)} GiB of {g(self.vram)} GiB -> {'FITS' if self.fits else 'DOES NOT FIT'}")


def estimate(weights_bytes: int, a: ModelArch, context: int, vram_bytes: int, kv_type: str = "f16",
             margin_gib: float = DEFAULT_MARGIN_GIB) -> Fit:
    return Fit(weights_bytes, kv_cache_bytes(a, context, kv_type), int(margin_gib * GIB), vram_bytes, context, kv_type)


def max_context(weights_bytes: int, a: ModelArch, vram_bytes: int, kv_type: str = "f16",
                margin_gib: float = DEFAULT_MARGIN_GIB) -> int:
    """Largest context (tokens, capped at the model's own limit) that still fits; 0 if even the weights do not."""
    room = vram_bytes - weights_bytes - int(margin_gib * GIB)
    per_token = kv_cache_bytes(a, 1, kv_type) or 1
    return max(0, min(a.max_context, room // per_token))


def read_nvidia_smi() -> list[dict]:
    """GPU name, total and free memory in MiB from `nvidia-smi --query-gpu=... --format=csv,noheader,nounits`."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = subprocess.run([exe, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=15, check=False).stdout
    return parse_nvidia_smi(out)


def parse_nvidia_smi(text: str) -> list[dict]:
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            gpus.append({"name": parts[0], "total_bytes": int(parts[1]) * 1024 ** 2, "free_bytes": int(parts[2]) * 1024 ** 2})
    return gpus
