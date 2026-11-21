"""Run every task through one agent per model, score deterministically, summarise, recommend routes."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

from .backend import Answer, Backend, agent_name_for
from .scoring import score


@dataclass
class Config:
    models: list[dict]            # [{"deployment": "gpt-4.1-mini", "label": "GPT-4.1 mini"}]
    instructions: str
    agent_prefix: str = "mglab-ep20"
    repeats: int = 1
    prices: dict = field(default_factory=dict)   # {"deployment": {"input_per_million": x, "output_per_million": y, "currency": "EUR"}}


def load_config(path: str | Path) -> Config:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not d.get("models"):
        raise ValueError("config needs at least one model")
    seen = set()
    for m in d["models"]:
        if "deployment" not in m:
            raise ValueError("every model needs a 'deployment' (the name of the deployment in your Foundry resource)")
        if m["deployment"] in seen:
            raise ValueError(f"duplicate deployment {m['deployment']}")
        seen.add(m["deployment"])
    return Config(models=d["models"], instructions=d["instructions"], agent_prefix=d.get("agent_prefix", "mglab-ep20"),
                  repeats=int(d.get("repeats", 1)), prices=d.get("prices", {}))


def load_tasks(path: str | Path) -> list[dict]:
    tasks = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task ids")
    for t in tasks:
        if not {"id", "category", "question", "checks"} <= t.keys():
            raise ValueError(f"task {t.get('id')} needs id, category, question, checks")
    return tasks


def planned_requests(cfg: Config, tasks: list[dict]) -> int:
    return len(cfg.models) * len(tasks) * cfg.repeats


def estimate_cost(model: str, input_tokens: int, output_tokens: int, prices: dict) -> float | None:
    p = prices.get(model)
    if not p:
        return None
    return input_tokens / 1e6 * p["input_per_million"] + output_tokens / 1e6 * p["output_per_million"]


def run(cfg: Config, tasks: list[dict], backend: Backend, max_requests: int = 200, keep_agents: bool = False) -> dict:
    n = planned_requests(cfg, tasks)
    if n > max_requests:
        raise ValueError(f"{n} requests planned, above --max-requests {max_requests}")
    rows, agents, setup_errors = [], [], {}
    try:
        for m in cfg.models:
            dep = m["deployment"]
            try:
                agents.append(backend.create_agent(agent_name_for(cfg.agent_prefix, dep), dep, cfg.instructions))
            except Exception as exc:  # noqa: BLE001 - e.g. deployment not found: report it, keep the other models
                setup_errors[dep] = f"{type(exc).__name__}: {exc}"
        for agent in agents:
            for task in tasks:
                for rep in range(cfg.repeats):
                    row = {"model": agent.model, "task": task["id"], "category": task["category"], "repeat": rep}
                    try:
                        ans: Answer = backend.ask(agent, task["question"])
                        s, checks = score(ans.text, task["checks"])
                        row.update(score=s, answer=ans.text, seconds=round(ans.seconds, 3), input_tokens=ans.input_tokens,
                                   output_tokens=ans.output_tokens, served_model=ans.served_model,
                                   failed=[c.rule for c in checks if not c.passed], error=None)
                    except Exception as exc:  # noqa: BLE001
                        row.update(score=0.0, answer="", seconds=None, input_tokens=None, output_tokens=None,
                                   served_model=None, failed=["request"], error=f"{type(exc).__name__}: {exc}")
                    rows.append(row)
    finally:
        if not keep_agents:
            for agent in agents:
                try:
                    backend.delete_agent(agent)
                except Exception as exc:  # noqa: BLE001
                    setup_errors[f"cleanup:{agent.name}"] = f"{type(exc).__name__}: {exc}"
    return {"instructions": cfg.instructions, "repeats": cfg.repeats, "rows": rows, "setupErrors": setup_errors,
            "prices": cfg.prices, "keptAgents": [a.name for a in agents] if keep_agents else []}


def summarise(result: dict) -> list[dict]:
    by_model: dict[str, list[dict]] = {}
    for r in result["rows"]:
        by_model.setdefault(r["model"], []).append(r)
    out = []
    for model, rows in by_model.items():
        ok = [r for r in rows if not r["error"]]
        tin = sum(r["input_tokens"] or 0 for r in ok)
        tout = sum(r["output_tokens"] or 0 for r in ok)
        cost = estimate_cost(model, tin, tout, result.get("prices", {}))
        out.append({"model": model, "requests": len(rows), "errors": len(rows) - len(ok),
                    "mean_score": round(mean(r["score"] for r in rows), 3),
                    "full_pass": sum(1 for r in rows if r["score"] == 1.0),
                    "mean_seconds": round(mean(r["seconds"] for r in ok), 2) if ok else None,
                    "input_tokens": tin, "output_tokens": tout,
                    "est_cost": round(cost, 6) if cost is not None else None})
    return sorted(out, key=lambda x: (-x["mean_score"], x["mean_seconds"] if x["mean_seconds"] is not None else 1e9))


def recommend_routes(result: dict, min_score: float = 0.9) -> dict:
    """Per task category: the cheapest model whose mean score reaches `min_score` (needs prices; otherwise the fastest)."""
    prices = result.get("prices", {})
    cats: dict[str, dict[str, list[dict]]] = {}
    for r in result["rows"]:
        cats.setdefault(r["category"], {}).setdefault(r["model"], []).append(r)
    routes = {}
    for cat, models in cats.items():
        cands = []
        for model, rows in models.items():
            sc = mean(r["score"] for r in rows)
            if sc < min_score:
                continue
            ok = [r for r in rows if not r["error"]]
            tin = sum(r["input_tokens"] or 0 for r in ok)
            tout = sum(r["output_tokens"] or 0 for r in ok)
            cost = estimate_cost(model, tin, tout, prices)
            secs = mean(r["seconds"] for r in ok) if ok else 1e9
            cands.append((cost if cost is not None else float("inf"), secs, model, round(sc, 3)))
        if cands:
            cost, secs, model, sc = sorted(cands)[0]
            routes[cat] = {"model": model, "mean_score": sc, "basis": "cheapest" if cost != float("inf") else "fastest (no prices given)"}
        else:
            routes[cat] = {"model": None, "mean_score": None, "basis": f"no model reached {min_score}"}
    return routes


def format_report(result: dict, min_score: float = 0.9) -> str:
    lines = ["| Model | Mean score | Full passes | Mean seconds | Tokens in/out | Est. cost | Errors |", "|---|---|---|---|---|---|---|"]
    for s in summarise(result):
        cost = "n/a" if s["est_cost"] is None else f"{s['est_cost']:.6f}"
        lines.append(f"| {s['model']} | {s['mean_score']:.2f} | {s['full_pass']}/{s['requests']} | {s['mean_seconds']} | "
                     f"{s['input_tokens']}/{s['output_tokens']} | {cost} | {s['errors']} |")
    lines += ["", f"Routing (cheapest model with mean score >= {min_score}):"]
    for cat, r in sorted(recommend_routes(result, min_score).items()):
        lines.append(f"- {cat}: {r['model'] or 'none'} ({r['basis']})")
    failed = [(r["model"], r["task"], r["failed"]) for r in result["rows"] if r["score"] < 1.0]
    if failed:
        lines += ["", "Failed checks:"] + [f"- {m} / {t}: {', '.join(f)}" for m, t, f in failed]
    if result.get("setupErrors"):
        lines += ["", "Setup errors:"] + [f"- {k}: {v}" for k, v in result["setupErrors"].items()]
    return "\n".join(lines)
