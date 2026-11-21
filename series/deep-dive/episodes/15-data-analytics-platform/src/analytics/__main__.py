"""python -m analytics <command>   (run from the `src` folder or with PYTHONPATH=src)"""
from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from . import ml, synthetic as syn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="analytics", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed-sql", help="write the MERGE script for one phase of the source data")
    p.add_argument("--phase", type=int, choices=(1, 2, 3), required=True,
                   help="1 = first load, 2 = later changes, 3 = four bad rows for the quality demo")
    p.add_argument("--out", required=True)

    p = sub.add_parser("make-bronze", help="write local bronze parquet files (offline dry run; the real ones come from Data Factory)")
    p.add_argument("--out", required=True)
    p.add_argument("--defects", action="store_true", help="add four bad rows to the second file")

    p = sub.add_parser("train", help="train on a lake folder that contains bronze/purchase_requests/...")
    p.add_argument("--lake", required=True)
    p.add_argument("--model", required=True, help="where to write model.json")

    p = sub.add_parser("export-sql", help="turn model.json into the gold.RequestRiskScore view")
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("drift", help="PSI of the amounts in the newest files against the training window")
    p.add_argument("--lake", required=True)
    p.add_argument("--model", required=True)

    a = ap.parse_args(argv)
    if a.cmd == "seed-sql":
        h = syn.generate_history()
        if a.phase == 3:
            df = syn.defect_rows(syn.delta(h, None, syn.T1), modified_on=syn.T3)
        else:
            df = syn.delta(h, None, syn.T1) if a.phase == 1 else syn.delta(h, syn.T1, syn.T2)
        pathlib.Path(a.out).write_text(syn.to_merge_sql(df), encoding="utf-8")
        print(f"phase {a.phase}: {len(df)} rows -> {a.out}")
    elif a.cmd == "make-bronze":
        h = syn.generate_history()
        first, second = syn.delta(h, None, syn.T1), syn.delta(h, syn.T1, syn.T2)
        if a.defects:
            second = syn.inject_defects(second)
        print(syn.write_bronze(first, a.out, "2026-10-31", "run1"))
        print(syn.write_bronze(second, a.out, "2026-11-14", "run2"))
    elif a.cmd == "train":
        model = ml.train(ml.load_training_frame(a.lake))
        ml.save(model, a.model)
        print(model["model_version"], model["metrics"])
    elif a.cmd == "export-sql":
        pathlib.Path(a.out).write_text(ml.export_sql(ml.load(a.model)), encoding="utf-8")
        print("written", a.out)
    elif a.cmd == "drift":
        model = ml.load(a.model)
        df = ml.load_training_frame(a.lake)
        cut = pd.Timestamp(model["training_window"][1])
        old, new = df[df["SubmittedDate"] <= cut], df[df["SubmittedDate"] > cut]
        value = ml.psi(old["Amount"].to_numpy(float), new["Amount"].to_numpy(float))
        print(f"PSI(amount) = {value:.3f} over {len(new)} newer requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
