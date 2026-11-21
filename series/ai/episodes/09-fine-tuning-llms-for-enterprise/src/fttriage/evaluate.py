"""Base model with the long prompt vs the fine-tuned model with the short prompt, on data neither has trained on.

Both are called the same way (chat completions, temperature 0, no response_format) and graded on the same items, so
the only differences are the model and the system prompt. A format error (not one valid JSON object) counts as wrong."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import openai

from .dataset import Example
from .labels import CATEGORIES, Label, parse_label

GATES = {
    "min_format_ok": 0.98,              # answers that parse as the contract
    "min_prompt_saving": 0.50,          # fewer input tokens than the baseline, as billed (usage.prompt_tokens)
    "min_needs_human_recall": 0.90,     # the safety metric: a sensitive message must not be waved through
}


@dataclass
class Call:
    example: Example
    raw: str | None
    label: Label | None
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    model: str = ""
    error: str | None = None


def run(client: openai.OpenAI, deployment: str, system: str, items: list[Example], *, max_tokens: int = 60) -> list[Call]:
    calls = []
    for ex in items:
        start = time.perf_counter()
        try:
            r = client.chat.completions.create(
                model=deployment, temperature=0, max_completion_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": ex.text}])
            raw = r.choices[0].message.content
            u = r.usage
            calls.append(Call(ex, raw, parse_label(raw), int((time.perf_counter() - start) * 1000),
                              getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0, r.model or ""))
        except openai.APIError as e:        # a failed call is a wrong answer, not a crash: record it and go on
            calls.append(Call(ex, None, None, int((time.perf_counter() - start) * 1000), 0, 0, "", type(e).__name__))
    return calls


def wilson(correct: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; honest about how little 30 or 46 items can say."""
    if n == 0:
        return (0.0, 0.0)
    p = correct / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def sign_test(only_a: int, only_b: int) -> float:
    """Exact two-sided sign test on the items where exactly one model is right (McNemar's exact test)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n * 2
    return min(1.0, p)


@dataclass
class Metrics:
    n: int
    format_ok: float
    category_acc: float
    category_ci: tuple[float, float]
    urgency_acc: float | None          # over items that carry an urgency label
    needs_human_acc: float | None
    needs_human_recall: float | None
    exact: float | None
    mean_prompt_tokens: float
    mean_completion_tokens: float
    mean_latency_ms: float
    wrong_by_category: dict[str, int] = field(default_factory=dict)


def metrics(calls: list[Call]) -> Metrics:
    n = len(calls)
    ok = [c for c in calls if c.label is not None]
    cat_right = sum(1 for c in calls if c.label and c.label.category == c.example.category)
    full = [c for c in calls if c.example.label is not None]
    urg = sum(1 for c in full if c.label and c.label.urgency == c.example.urgency)
    hum = sum(1 for c in full if c.label and c.label.needs_human == c.example.needs_human)
    exact = sum(1 for c in full if c.label and c.label == c.example.label)
    pos = [c for c in full if c.example.needs_human]
    recall = sum(1 for c in pos if c.label and c.label.needs_human) / len(pos) if pos else None
    wrong: dict[str, int] = {}
    for c in calls:
        if not (c.label and c.label.category == c.example.category):
            wrong[c.example.category] = wrong.get(c.example.category, 0) + 1
    served = [c for c in calls if c.prompt_tokens]
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    return Metrics(
        n=n, format_ok=len(ok) / n if n else 0.0, category_acc=cat_right / n if n else 0.0,
        category_ci=wilson(cat_right, n),
        urgency_acc=urg / len(full) if full else None, needs_human_acc=hum / len(full) if full else None,
        needs_human_recall=recall, exact=exact / len(full) if full else None,
        mean_prompt_tokens=mean([c.prompt_tokens for c in served]),
        mean_completion_tokens=mean([c.completion_tokens for c in served]),
        mean_latency_ms=mean([c.latency_ms for c in calls]),
        wrong_by_category={k: wrong[k] for k in sorted(wrong, key=lambda k: CATEGORIES.index(k))},
    )


@dataclass
class Comparison:
    base: Metrics
    tuned: Metrics
    only_base_right: int
    only_tuned_right: int
    p_value: float
    prompt_saving: float
    verdicts: dict[str, bool]

    @property
    def promote(self) -> bool:
        return all(self.verdicts.values())


def compare(base_calls: list[Call], tuned_calls: list[Call], gates: dict | None = None) -> Comparison:
    gates = gates or GATES
    if [c.example.id for c in base_calls] != [c.example.id for c in tuned_calls]:
        raise ValueError("both models must be graded on the same items in the same order")
    b, t = metrics(base_calls), metrics(tuned_calls)
    right = lambda c: bool(c.label and c.label.category == c.example.category)
    only_b = sum(1 for x, y in zip(base_calls, tuned_calls) if right(x) and not right(y))
    only_t = sum(1 for x, y in zip(base_calls, tuned_calls) if right(y) and not right(x))
    saving = 1 - t.mean_prompt_tokens / b.mean_prompt_tokens if b.mean_prompt_tokens else 0.0
    verdicts = {
        "format": t.format_ok >= gates["min_format_ok"],
        "category: not worse than the baseline": t.category_acc >= b.category_acc,
        "needs_human recall": (t.needs_human_recall is None) or t.needs_human_recall >= gates["min_needs_human_recall"],
        "prompt tokens saved": saving >= gates["min_prompt_saving"],
    }
    return Comparison(b, t, only_b, only_t, sign_test(only_b, only_t), saving, verdicts)


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render(cmp: Comparison, base_name: str = "base + long prompt", tuned_name: str = "fine-tuned + short prompt") -> str:
    b, t = cmp.base, cmp.tuned
    lo_b, hi_b = b.category_ci
    lo_t, hi_t = t.category_ci
    rows = [
        ("items", f"{b.n}", f"{t.n}"),
        ("valid JSON answers", pct(b.format_ok), pct(t.format_ok)),
        ("category accuracy", pct(b.category_acc), pct(t.category_acc)),
        ("  95% interval", f"{pct(lo_b)} to {pct(hi_b)}", f"{pct(lo_t)} to {pct(hi_t)}"),
        ("urgency accuracy", pct(b.urgency_acc), pct(t.urgency_acc)),
        ("needs_human accuracy", pct(b.needs_human_acc), pct(t.needs_human_acc)),
        ("needs_human recall", pct(b.needs_human_recall), pct(t.needs_human_recall)),
        ("all three right", pct(b.exact), pct(t.exact)),
        ("input tokens / call", f"{b.mean_prompt_tokens:.0f}", f"{t.mean_prompt_tokens:.0f}"),
        ("mean latency (ms)", f"{b.mean_latency_ms:.0f}", f"{t.mean_latency_ms:.0f}"),
    ]
    w = max(len(r[0]) for r in rows)
    out = [f"{'':{w}}  {base_name:>26}  {tuned_name:>26}"]
    out += [f"{a:{w}}  {x:>26}  {y:>26}" for a, x, y in rows]
    out.append("")
    out.append(f"category: only the base was right on {cmp.only_base_right} items, only the tuned model on "
               f"{cmp.only_tuned_right} (exact sign test p = {cmp.p_value:.2f}); input tokens saved {pct(cmp.prompt_saving)}")
    for name, ok in cmp.verdicts.items():
        out.append(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    out.append("PROMOTE" if cmp.promote else "DO NOT PROMOTE")
    return "\n".join(out)
