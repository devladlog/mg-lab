"""Sampling settings: how much does the answer move between identical requests?
temperature rescales the next-token distribution before one token is drawn; `seed` asks for a best-effort
deterministic draw (Learn: preview, not guaranteed, watch `system_fingerprint`). We measure instead of assuming:
the same prompt N times per setting, wording variation versus the facts that must survive."""
from __future__ import annotations

import difflib
import itertools
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Setting:
    temperature: float
    seed: int | None

    @property
    def label(self) -> str:
        return f"t={self.temperature:g}" + (f" seed={self.seed}" if self.seed is not None else " no seed")


DEFAULT_SETTINGS = (Setting(0, None), Setting(0, 42), Setting(1, None), Setting(1, 42))


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def mean_similarity(texts: list[str]) -> float:
    pairs = list(itertools.combinations(texts, 2))
    if not pairs:
        return 1.0
    return sum(similarity(a, b) for a, b in pairs) / len(pairs)


def facts_present(text: str, facts: list[str]) -> bool:
    """Every required fact (a regular expression) must appear in the answer."""
    return all(re.search(f, text, re.IGNORECASE) for f in facts)


def run_setting(client, deployment: str, messages: list[dict], setting: Setting, runs: int, max_tokens: int = 200) -> dict:
    outputs, prints, finish = [], set(), []
    for _ in range(runs):
        kw = {"temperature": setting.temperature, "max_completion_tokens": max_tokens}
        if setting.seed is not None:
            kw["seed"] = setting.seed
        r = client.chat.completions.create(model=deployment, messages=messages, **kw)
        outputs.append((r.choices[0].message.content or "").strip())
        finish.append(r.choices[0].finish_reason)
        prints.add(getattr(r, "system_fingerprint", None))
    return {"setting": setting, "outputs": outputs, "fingerprints": sorted(p for p in prints if p), "finish": finish}


def summarise(result: dict, facts: list[str]) -> dict:
    outs = result["outputs"]
    return {
        "label": result["setting"].label,
        "runs": len(outs),
        "distinct": len(set(outs)),
        "mean_similarity": mean_similarity(outs),
        "fact_rate": sum(facts_present(o, facts) for o in outs) / len(outs) if outs else 0.0,
        "truncated": sum(f == "length" for f in result["finish"]),
        "fingerprints": result["fingerprints"],
    }


def failing(summaries: list[dict], min_fact_rate: float = 1.0) -> list[str]:
    """Reasons to stop: a setting where a required fact went missing, or an answer was cut off."""
    why = []
    for s in summaries:
        if s["fact_rate"] < min_fact_rate:
            why.append(f"{s['label']}: facts present in {s['fact_rate']:.0%} of runs (needs {min_fact_rate:.0%})")
        if s["truncated"]:
            why.append(f"{s['label']}: {s['truncated']} answer(s) cut off by max_completion_tokens")
    return why


def render(summaries: list[dict]) -> str:
    lines = [f"{'setting':<18}{'runs':>5}{'distinct':>9}{'similarity':>11}{'facts ok':>9}  fingerprints"]
    for s in summaries:
        lines.append(f"{s['label']:<18}{s['runs']:>5}{s['distinct']:>9}{s['mean_similarity']:>11.2f}{s['fact_rate']:>9.0%}  "
                     f"{','.join(s['fingerprints']) or '-'}")
    return "\n".join(lines)
