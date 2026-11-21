"""python -m mlbasics data | audit | baseline | compare | depth | train | score"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import audit, card, data, experiments, report


def _frame(a) -> pd.DataFrame:
    if getattr(a, "csv", None):
        return pd.read_csv(a.csv)
    kw = {}
    if a.seed is not None:
        kw["seed"] = a.seed
    if a.rows is not None:
        kw.update(n=a.rows, requesters=max(20, a.rows // 16))
    return data.generate(**kw)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mlbasics")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--csv", help="use this table instead of generating the synthetic one")
        p.add_argument("--seed", type=int, default=None, help="seed of the synthetic data (default: the committed one)")
        p.add_argument("--rows", type=int, default=None, help="number of synthetic tickets (default 8000)")

    d = sub.add_parser("data", help="write the synthetic tickets to a CSV")
    common(d)
    d.add_argument("--out", default="build/tickets.csv")
    a_ = sub.add_parser("audit", help="class balance, missing values, leakage scan; exit 1 if a column is suspect")
    common(a_)
    a_.add_argument("--drop", nargs="*", default=[], help="columns to remove before the scan (for example first_response_minutes)")
    b = sub.add_parser("baseline", help="accuracy versus a model with no skill")
    common(b)
    c = sub.add_parser("compare", help="the same models under five evaluation protocols")
    common(c)
    dp = sub.add_parser("depth", help="train vs validation score as a tree gets deeper")
    common(dp)
    t = sub.add_parser("train", help="grouped CV, threshold from costs, one test evaluation, model card; exit 1 if it does not beat doing nothing")
    common(t)
    t.add_argument("--out", default="build")
    t.add_argument("--cost-fn", type=float, default=10.0, help="cost of a missed breach")
    t.add_argument("--cost-fp", type=float, default=1.0, help="cost of a false alarm")
    t.add_argument("--min-lift", type=float, default=2.0)
    s = sub.add_parser("score", help="risk for one new ticket (a JSON file)")
    s.add_argument("ticket")
    s.add_argument("--model", default="build/model.joblib")
    s.add_argument("--card", default="build/model_card.json")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return _run(a)
    except (card.ScoreError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _run(a) -> int:
    if a.cmd == "score":
        r = card.score_ticket(a.model, a.card, json.loads(Path(a.ticket).read_text(encoding="utf-8")))
        print(f"risk {r['risk']:.3f}  threshold {r['threshold']:.3f}  -> " + ("FLAG for the dispatcher" if r["flag_for_dispatcher"] else "normal queue"))
        return 0
    df = _frame(a)
    if a.cmd == "data":
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(a.out, index=False)
        print(f"{a.out}: {len(df):,} rows, fingerprint {data.fingerprint(df)}")
        return 0
    if a.cmd == "audit":
        df = df.drop(columns=a.drop)
        print(audit.render(df))
        return 1 if any(r["suspect"] for r in audit.leakage_scan(df)) else 0
    if a.cmd == "baseline":
        print(report.baseline(experiments.baseline(df)))
        return 0
    if a.cmd == "compare":
        print(report.protocols(experiments.compare_protocols(df)))
        return 0
    if a.cmd == "depth":
        print(report.depth(experiments.depth_curve(df)))
        return 0
    res = experiments.train_and_test(df, a.cost_fn, a.cost_fp)
    ok, why = experiments.verdict(res, a.min_lift)
    print(report.training(res, ok, why))
    mp, cp = card.save(res, card.make_card(df, res), a.out)
    print(f"saved {mp} and {cp}")
    return 0 if ok else 1
