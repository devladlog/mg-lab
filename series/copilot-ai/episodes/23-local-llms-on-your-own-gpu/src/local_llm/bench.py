"""Tokens per second on your own GPU, from the timings Ollama reports. First run is a warm-up (it includes model load)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .ollama import ChatResult, OllamaClient, placement


@dataclass
class BenchSummary:
    model: str
    runs: list[ChatResult]
    warmup: ChatResult
    placement: str
    context_length: int

    @property
    def gen_tps_median(self) -> float:
        return statistics.median(r.gen_tps for r in self.runs) if self.runs else 0.0

    @property
    def prompt_tps_median(self) -> float:
        return statistics.median(r.prompt_tps for r in self.runs) if self.runs else 0.0

    def row(self) -> str:
        return (f"| {self.model} | {self.placement} | {self.context_length} | {self.warmup.load_s:.1f} | "
                f"{self.prompt_tps_median:.0f} | {self.gen_tps_median:.1f} | {len(self.runs)} |")


HEADER = ("| model | placement (from /api/ps) | context | load s (warm-up) | prompt tok/s | generation tok/s | runs |\n"
          "|---|---|---|---|---|---|---|")


def run_bench(client: OllamaClient, model: str, prompt: str, repeats: int = 3, num_predict: int = 200,
              num_ctx: int | None = None, keep_alive: str | int | None = "5m", think: bool | None = False) -> BenchSummary:
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    opts: dict = {"num_predict": num_predict, "seed": 1}
    if num_ctx:
        opts["num_ctx"] = num_ctx
    msgs = [{"role": "user", "content": prompt}]
    warm = client.chat(model, msgs, options=opts, keep_alive=keep_alive, think=think)
    runs = [client.chat(model, msgs, options=opts, keep_alive=keep_alive, think=think) for _ in range(repeats)]
    loaded = next((m for m in client.ps() if m.get("name") == model or m.get("model") == model), {})
    return BenchSummary(model, runs, warm, placement(loaded), int(loaded.get("context_length", 0) or 0))
