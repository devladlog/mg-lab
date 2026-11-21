"""Retrieval scorecard: the same labelled questions through every retrieval mode.

    PYTHONPATH=src python -m hrrag.evaluate --local                       # offline test double (plumbing only)
    PYTHONPATH=src python -m hrrag.evaluate --search-endpoint https://<search>.search.windows.net

Metrics per mode, over the answerable questions (expected section known):
- hit@1 / hit@k: share of questions whose expected section is the first result / in the top k
- MRR: mean of 1/rank of the first correct result (0 when it's missing)
Out-of-scope questions are listed separately with their top result, because "what came back for a question the
handbook can't answer" is exactly what the answer step must be able to refuse.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .hits import Hit

Retriever = Callable[[str, str, int], list[Hit]]


@dataclass
class Score:
    mode: str
    n: int
    hit1: float
    hitk: float
    mrr: float
    misses: list[str]


def load_questions(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def first_correct_rank(hits: Sequence[Hit], expected: Sequence[str]) -> int | None:
    for rank, h in enumerate(hits, start=1):
        if h.section_key in expected:
            return rank
    return None


def score_mode(retrieve: Retriever, questions: Sequence[dict], mode: str, k: int = 5) -> Score:
    answerable = [q for q in questions if q["expected"]]
    ranks, misses = [], []
    for q in answerable:
        rank = first_correct_rank(retrieve(q["question"], mode, k), q["expected"])
        ranks.append(rank)
        if rank is None:
            misses.append(q["id"])
    n = len(answerable)
    return Score(
        mode, n,
        hit1=sum(1 for r in ranks if r == 1) / n,
        hitk=sum(1 for r in ranks if r is not None) / n,
        mrr=sum(1 / r for r in ranks if r) / n,
        misses=misses,
    )


def scorecard(scores: Sequence[Score], k: int) -> str:
    lines = [f"{'mode':16} {'hit@1':>6} {'hit@' + str(k):>6} {'MRR':>6}  misses", "-" * 60]
    for s in scores:
        lines.append(f"{s.mode:16} {s.hit1:6.2f} {s.hitk:6.2f} {s.mrr:6.2f}  {' '.join(s.misses) or '-'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from .retrieve import MODES

    p = argparse.ArgumentParser(prog="hrrag.evaluate", description="Compare retrieval modes on labelled questions.")
    p.add_argument("--questions", default="data/questions.jsonl")
    p.add_argument("--data", default="data/handbook", help="handbook folder (only for --local)")
    p.add_argument("--local", action="store_true", help="use the offline test double instead of Azure AI Search")
    p.add_argument("--search-endpoint")
    p.add_argument("--index", default="hr-handbook")
    p.add_argument("--mode", action="append", choices=MODES)
    p.add_argument("--k", type=int, default=5)
    a = p.parse_args(argv)
    questions = load_questions(a.questions)
    modes = a.mode or list(MODES)
    if a.local:
        from .chunking import chunk_folder
        from .local import LocalIndex

        index = LocalIndex(chunk_folder(a.data))
        retrieve: Retriever = lambda q, m, k: index.search(q, m, k)  # noqa: E731
        print("LOCAL TEST DOUBLE: hashed lexical vectors, no semantic ranker. Plumbing check, not a benchmark.\n")
    else:
        if not a.search_endpoint:
            p.error("--search-endpoint is required unless --local")
        from .retrieve import AzureRetriever

        retrieve = AzureRetriever(a.search_endpoint, a.index)
    scores = [score_mode(retrieve, questions, m, a.k) for m in modes]
    print(scorecard(scores, a.k))
    out_of_scope = [q for q in questions if not q["expected"]]
    if out_of_scope:
        print(f"\nout of scope (top result per question, mode {modes[-1]}):")
        for q in out_of_scope:
            hits = retrieve(q["question"], modes[-1], 1)
            top = hits[0] if hits else None
            rr = f" reranker={top.reranker_score:.2f}" if top and top.reranker_score is not None else ""
            print(f"  {q['id']} {q['question'][:48]:48} -> {top.section_key if top else '(nothing)'}{rr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
