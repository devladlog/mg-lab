from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cost as costmod
from . import describe as descmod
from . import golden as goldmod
from .lint import (Finding, lint_instructions, lint_model, lint_verified, load_plan, summarise)
from .tmdl import load_model

SEV_ORDER = {"info": 0, "warning": 1, "error": 2}


def _print_findings(findings: list[Finding]) -> None:
    for f in sorted(findings, key=lambda x: (-SEV_ORDER[x.severity], x.rule, x.where)):
        print(f"{f.severity.upper():7} {f.rule}  {f.where}: {f.message}")
    s = summarise(findings)
    print(f"-- {s['error']} errors, {s['warning']} warnings, {s['info']} info")


def cmd_lint(a) -> int:
    model = load_model(a.model)
    findings = lint_model(model)
    if a.instructions:
        findings += lint_instructions(model, Path(a.instructions).read_text(encoding="utf-8"))
    if a.verified:
        findings += lint_verified(load_plan(a.verified))
    if a.json:
        print(json.dumps({"model": model.path, "summary": summarise(findings),
                          "findings": [f.as_dict() for f in findings]}, indent=2))
    else:
        n_m, n_c = len(model.measures()), len(model.columns())
        print(f"model: {len(model.tables)} tables, {n_c} columns, {n_m} measures ({model.path})")
        _print_findings(findings)
    threshold = SEV_ORDER[a.fail_on]
    return 1 if any(SEV_ORDER[f.severity] >= threshold for f in findings) else 0


def cmd_cost(a) -> int:
    e = costmod.estimate(a.sku, a.prompts_per_day, a.input_tokens, a.output_tokens, a.cached_share,
                         a.price_per_cu_hour, a.window_hours)
    cur = a.currency
    print(f"Copilot in Fabric, rates checked {costmod.RATES_CHECKED} (100 / 10 / 400 CU seconds per 1,000 tokens)")
    print(f"SKU {e.sku}: {e.cu} CU")
    print(f"one prompt: {e.cu_seconds_per_prompt:,.1f} CU seconds ({e.cu_seconds_per_prompt / 60:,.2f} CU minutes)")
    print(f"{e.prompts_per_day:,} prompts/day: {e.cu_seconds_per_day / 3600:,.2f} CU hours = "
          f"{e.share_of_daily_capacity * 100:,.2f}% of a day of {e.sku}")
    print(f"prompts per day that would use the whole capacity: {e.prompts_per_day_to_exhaust:,.0f}")
    if e.capacity_cost_per_hour is not None:
        print(f"capacity price: {e.capacity_cost_per_hour:,.3f} {cur}/hour while running (price you supplied)")
        if e.window_cost is not None:
            print(f"recording window {e.window_hours:g} h: {e.window_cost:,.2f} {cur}")
    return 0


def cmd_golden(a) -> int:
    star = a.data or goldmod.default_star_dir()
    if not star:
        print("star-schema data folder not found: pass --data", file=sys.stderr)
        return 2
    rows = goldmod.compute(star, a.year, a.month)
    if a.json:
        print(json.dumps([{k: v for k, v in r.items() if k != "raw"} for r in rows], indent=2))
    else:
        for r in rows:
            print(f"{r['id']}  {r['question']}")
            print(f"    measure {r['measure']}, by {r['grouping']}, date basis: {r['date_basis']}")
            print(f"    validated result: {r['expected']}")
    return 0


def cmd_describe(a) -> int:
    spec = descmod.load_spec(a.spec)
    n = descmod.apply_descriptions(a.model, a.out, spec)
    print(f"{n} descriptions written to the copy in {a.out}; the source model was not changed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="copilot_pbi", description="Copilot readiness checks for Power BI semantic models")
    sub = p.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("lint", help="check a TMDL semantic model (and optional AI instructions / verified-answer plan)")
    l.add_argument("model", help="folder with definition/ (a *.SemanticModel folder) or the definition folder itself")
    l.add_argument("--instructions", help="text file with the AI instructions you will paste into Prep data for AI")
    l.add_argument("--verified", help="JSON plan of verified answers (our format, see data/verified-answers-plan.json)")
    l.add_argument("--json", action="store_true")
    l.add_argument("--fail-on", choices=["error", "warning", "info"], default="error")
    l.set_defaults(fn=cmd_lint)

    c = sub.add_parser("cost", help="estimate Copilot capacity use from the documented token rates")
    c.add_argument("--sku", default="F2")
    c.add_argument("--prompts-per-day", type=int, default=200)
    c.add_argument("--input-tokens", type=int, default=8000, help="prompt + grounding tokens per request")
    c.add_argument("--output-tokens", type=int, default=600)
    c.add_argument("--cached-share", type=float, default=0.0, help="share of input tokens served from cache, 0..1")
    c.add_argument("--price-per-cu-hour", type=float, help="your own price for one CU hour (see README for the source)")
    c.add_argument("--window-hours", type=float, help="hours the capacity runs, to price a recording")
    c.add_argument("--currency", default="EUR")
    c.set_defaults(fn=cmd_cost)

    g = sub.add_parser("golden", help="validated answers for the golden questions, computed from the CSV files")
    g.add_argument("--data", help="folder with fact_sales.csv and dim_*.csv (default: Power BI episode 1)")
    g.add_argument("--year", type=int, default=2025)
    g.add_argument("--month", type=int, default=6, help="month used by the ship-date question")
    g.add_argument("--json", action="store_true")
    g.set_defaults(fn=cmd_golden)

    d = sub.add_parser("describe", help="copy a model and add descriptions from a JSON spec")
    d.add_argument("model")
    d.add_argument("spec")
    d.add_argument("--out", required=True, help="new folder for the described copy (must not exist)")
    d.set_defaults(fn=cmd_describe)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
