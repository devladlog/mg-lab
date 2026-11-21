"""Streaming: what the user waits for. Time to the first content chunk, total time, and a reminder that chunks are
not tokens (default streaming buffers content for the content filter; Learn: 'content chunks of the respective
buffer size'). The first chunk can carry only filter annotations (empty `choices`) and, with
`stream_options.include_usage`, the last chunk carries only `usage`: both must be skipped, not crash."""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field


@dataclass
class StreamStats:
    first_chunk_s: float
    first_content_s: float | None
    total_s: float
    chunks: int
    content_chunks: int
    chars: int
    completion_tokens: int | None
    prompt_tokens: int | None
    finish_reason: str | None
    text: str = field(repr=False, default="")


def stream_once(client, deployment: str, messages: list[dict], max_tokens: int = 300, clock=time.perf_counter) -> StreamStats:
    t0 = clock()
    stream = client.chat.completions.create(
        model=deployment, messages=messages, stream=True, stream_options={"include_usage": True},
        temperature=0, max_completion_tokens=max_tokens,
    )
    first_chunk = first_content = None
    chunks = content_chunks = 0
    parts, usage, finish = [], None, None
    for ch in stream:
        now = clock() - t0
        chunks += 1
        if first_chunk is None:
            first_chunk = now
        if getattr(ch, "usage", None) is not None:
            usage = ch.usage
        if not ch.choices:               # filter annotations (first) or the usage chunk (last)
            continue
        c = ch.choices[0]
        if c.delta is not None and c.delta.content:
            content_chunks += 1
            parts.append(c.delta.content)
            if first_content is None:
                first_content = now
        if c.finish_reason:
            finish = c.finish_reason
    total = clock() - t0
    text = "".join(parts)
    return StreamStats(first_chunk or 0.0, first_content, total, chunks, content_chunks, len(text),
                       getattr(usage, "completion_tokens", None), getattr(usage, "prompt_tokens", None), finish, text)


def blocking_once(client, deployment: str, messages: list[dict], max_tokens: int = 300, clock=time.perf_counter) -> float:
    t0 = clock()
    client.chat.completions.create(model=deployment, messages=messages, temperature=0, max_completion_tokens=max_tokens)
    return clock() - t0


def summarise(streamed: list[StreamStats], blocking: list[float]) -> dict:
    firsts = [s.first_content_s for s in streamed if s.first_content_s is not None]
    return {
        "runs": len(streamed),
        "first_content_median_s": statistics.median(firsts) if firsts else None,
        "stream_total_median_s": statistics.median(s.total_s for s in streamed),
        "blocking_total_median_s": statistics.median(blocking) if blocking else None,
        "content_chunks_median": statistics.median(s.content_chunks for s in streamed),
        "completion_tokens_median": statistics.median(s.completion_tokens for s in streamed if s.completion_tokens is not None)
        if any(s.completion_tokens is not None for s in streamed) else None,
    }


def render(sm: dict) -> str:
    def f(x):
        return "-" if x is None else f"{x:.2f}s" if isinstance(x, float) else str(x)
    return "\n".join([
        f"runs                         {sm['runs']}",
        f"streaming: first content     {f(sm['first_content_median_s'])}   (median)",
        f"streaming: complete          {f(sm['stream_total_median_s'])}",
        f"blocking:  complete          {f(sm['blocking_total_median_s'])}",
        f"content chunks / run         {f(sm['content_chunks_median'])}",
        f"completion tokens / run      {f(sm['completion_tokens_median'])}   (billed, from the usage chunk)",
    ])
