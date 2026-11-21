"""Run tasks x providers x repeats, score, summarise, report. Providers are isolated: one failure never stops the run."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from . import providers as prov
from . import scoring


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    ids = [p["id"] for p in cfg.get("providers", [])]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("config needs providers with unique ids")
    return cfg


def build_providers(cfg: dict, only: list[str] | None = None, transport=None, base_dir: Path | None = None) -> list[prov.Provider]:
    chosen = [p for p in cfg["providers"] if not only or p["id"] in only]
    if only and len(chosen) != len(set(only)):
        missing = set(only) - {p["id"] for p in chosen}
        raise ValueError(f"unknown provider id(s): {sorted(missing)}")
    merged = []
    for p in chosen:
        merged.append({"max_tokens": cfg.get("max_tokens", 1500), **p})
    return [prov.build(p, transport, base_dir) for p in merged]


def prompt_for(cfg: dict, task: dict) -> tuple[str | None, str]:
    """The exact text every AI receives (also what is pasted into Copilot Chat)."""
    return prov.build_prompt(cfg.get("instructions", ""), task["question"], cfg.get("instructions_mode", "inline"))


def plan(cfg: dict, tasks: list[dict], providers: list[prov.Provider], repeats: int) -> list[str]:
    lines = [f"{len(providers)} providers x {len(tasks)} tasks x {repeats} repeat(s) = {len(providers) * len(tasks) * repeats} answers"]
    for p in providers:
        issues = p.problems()
        lines.append(f"  {p.id:10} {p.kind:10} {p.model or '-':28} " + ("OK" if not issues else "PROBLEM: " + "; ".join(issues)))
    return lines


def run(cfg: dict, tasks: list[dict], providers: list[prov.Provider], repeats: int = 1, allow_exec: bool = False,
        progress=None) -> dict:
    rows = []
    for p in providers:
        manual = p.kind == "manual"
        for t in tasks:
            system, user = prompt_for(cfg, t)
            for r in range(1 if manual else repeats):
                reply = p.ask(system, user, t["id"])
                checks = [] if reply.error else scoring.run_checks(reply.text, t.get("checks", {}), allow_exec)
                rows.append({"provider": p.id, "task": t["id"], "category": t.get("category", ""), "repeat": r,
                             "answer": reply.text, "error": reply.error, "note": reply.note,
                             "score": 0.0 if reply.error else round(scoring.score(checks), 3),
                             "checks": [c.__dict__ for c in checks], "input_tokens": reply.input_tokens,
                             "output_tokens": reply.output_tokens, "seconds": reply.seconds})
                if progress:
                    progress(rows[-1])
    return {"meta": {"providers": {p.id: {"label": p.label, "kind": p.kind, "model": p.model} for p in providers},
                     "instructions_mode": cfg.get("instructions_mode", "inline"), "repeats": repeats,
                     "prices": cfg.get("prices", {}), "code_exec": allow_exec, "tasks": len(tasks)},
            "rows": rows}


def cost(prices: dict, provider_id: str, tin: int, tout: int) -> float:
    p = prices.get(provider_id) or {}
    return (tin * p.get("input_per_million", 0.0) + tout * p.get("output_per_million", 0.0)) / 1e6


def summarise(results: dict) -> dict[str, dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in results["rows"]:
        by[r["provider"]].append(r)
    out = {}
    for pid, rows in by.items():
        secs = [r["seconds"] for r in rows if r["seconds"] is not None and not r["error"]]
        human = [r["human_score"] for r in rows if r.get("human_score") is not None]
        tin, tout = sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows)
        out[pid] = {"mean_score": statistics.mean(r["score"] for r in rows), "full_passes": sum(r["score"] == 1.0 for r in rows),
                    "answers": len(rows), "errors": sum(bool(r["error"]) for r in rows),
                    "mean_seconds": statistics.mean(secs) if secs else None, "input_tokens": tin, "output_tokens": tout,
                    "cost": cost(results["meta"].get("prices", {}), pid, tin, tout),
                    "human_mean": statistics.mean(human) if human else None}
    return out


def _f(v, fmt):
    return "-" if v is None else format(v, fmt)


def report(results: dict) -> str:
    meta, s = results["meta"], summarise(results)
    lines = [f"Instructions mode: {meta['instructions_mode']}; {meta['tasks']} tasks; repeats {meta['repeats']}; "
             f"code execution {'on' if meta.get('code_exec') else 'OFF (code tasks score 0 on the python checks)'}", "",
             "| provider | model | mean score | full passes | errors | mean s | tokens in/out | est. cost | human 1-5 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for pid, v in sorted(s.items(), key=lambda kv: -kv[1]["mean_score"]):
        m = meta["providers"][pid]
        lines.append(f"| {m['label']} | {m['model'] or 'n/a'} | {v['mean_score']:.2f} | {v['full_passes']}/{v['answers']} | {v['errors']} | "
                     f"{_f(v['mean_seconds'], '.1f')} | {v['input_tokens']}/{v['output_tokens']} | {v['cost']:.4f} | {_f(v['human_mean'], '.1f')} |")
    lines += ["", "Mean score by category:", "", "| category | " + " | ".join(meta["providers"]) + " |",
              "|---|" + "---|" * len(meta["providers"])]
    cats = sorted({r["category"] for r in results["rows"]})
    for c in cats:
        cells = []
        for pid in meta["providers"]:
            sc = [r["score"] for r in results["rows"] if r["provider"] == pid and r["category"] == c]
            cells.append(f"{statistics.mean(sc):.2f}" if sc else "-")
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    fails = [(r["provider"], r["task"], c) for r in results["rows"] for c in r["checks"] if not c["passed"]]
    errs = [r for r in results["rows"] if r["error"]]
    if errs:
        lines += ["", "Errors (scored 0, never retried silently):"] + [f"- {r['provider']} / {r['task']}: {r['error']}" for r in errs]
    if fails:
        lines += ["", "Failed checks:"] + [f"- {p} / {t}: {c['rule']} {('(' + c['detail'] + ')') if c['detail'] else ''}" for p, t, c in fails]
    lines += ["", "Prices come from the config (placeholders are zero): read each vendor's price page before trusting the cost column.",
              "Seconds are not measured for human-collected (manual) answers."]
    return "\n".join(lines)
