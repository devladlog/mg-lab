"""python -m slabreach generate | prepare | train | evaluate | check-request. The three components call prepare, train, evaluate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="slabreach")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write a fictional ticket history (tickets.csv)")
    g.add_argument("--out", required=True)
    g.add_argument("--rows", type=int, default=6000)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--scenario", default="baseline", choices=["baseline", "noisy", "missing-column"])
    pr = sub.add_parser("prepare")
    pr.add_argument("--raw", required=True)
    pr.add_argument("--train-out", required=True)
    pr.add_argument("--test-out", required=True)
    pr.add_argument("--test-fraction", type=float, default=0.2)
    t = sub.add_parser("train")
    t.add_argument("--train", required=True)
    t.add_argument("--model-out", required=True)
    t.add_argument("--seed", type=int, default=7)
    t.add_argument("--max-iter", type=int, default=120)
    e = sub.add_parser("evaluate")
    e.add_argument("--model", required=True)
    e.add_argument("--test", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--baseline-auc", type=float, default=0.0, help="AUC of the model now in production (0 = none yet)")
    c = sub.add_parser("check-request", help="run a request file through the MLflow model the way the endpoint's scoring script does")
    c.add_argument("--model", required=True)
    c.add_argument("--request", required=True)
    a = p.parse_args(argv)

    if a.cmd == "generate":
        from .data import generate
        from .schema import RAW_FILE
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        df = generate(a.rows, a.seed, a.scenario)
        df.to_csv(out / RAW_FILE, index=False)
        print(f"wrote {len(df)} rows ({a.scenario}, seed {a.seed}) to {out / RAW_FILE}")
        return 0
    if a.cmd == "prepare":
        from .prepare import run
        return run(Path(a.raw), Path(a.train_out), Path(a.test_out), a.test_fraction)
    if a.cmd == "train":
        from .train import run
        run(Path(a.train), Path(a.model_out), a.seed, a.max_iter)
        return 0
    if a.cmd == "evaluate":
        from .evaluate import run
        return run(Path(a.model), Path(a.test), Path(a.out), a.baseline_auc)
    from .serving import predict_request
    print(json.dumps(predict_request(Path(a.model), Path(a.request))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
