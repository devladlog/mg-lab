"""python -m fttriage <command>:  prepare | submit | deploy | evaluate | cleanup | cost"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dataset, economics, evaluate, jobs, tokens, validate
from .prompts import SHORT_SYSTEM, baseline_system

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def prepare(args) -> int:
    ex = dataset.load_labelled(args.labelled)
    golden = dataset.load_golden(args.golden)
    sp = dataset.split(ex, seed=args.seed)
    out = Path(args.out)
    train_rows = [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.train]
    val_rows = [dataset.to_chat(e, SHORT_SYSTEM) for e in sp.validation]
    dataset.write_jsonl(out / "training.jsonl", train_rows)
    dataset.write_jsonl(out / "validation.jsonl", val_rows)
    test_cases = sp.test + golden
    dataset.write_jsonl(out / "test.jsonl", [{"id": e.id, "text": e.text, "category": e.category, "urgency": e.urgency,
                                              "needs_human": e.needs_human} for e in test_cases], bom=False)

    held_out = {"validation": [e.text for e in sp.validation], "test": [e.text for e in sp.test],
                "episode 8 golden set": [e.text for e in golden]}
    report = validate.merge(
        validate.check_rows(train_rows, "training"), validate.check_rows(val_rows, "validation"),
        validate.check_leakage(train_rows, held_out),
        validate.check_file_encoding(out / "training.jsonl"), validate.check_file_encoding(out / "validation.jsonl"))
    for i in report.issues:
        print(f"{i.severity.upper():7} {i.code}: {i.message} {('(' + i.where + ')') if i.where else ''}")
    t_tokens = tokens.count_rows(train_rows)
    base_prompt, short_prompt = tokens.count_text(baseline_system()), tokens.count_text(SHORT_SYSTEM)
    langs = {l: sum(1 for e in sp.train if e.lang == l) for l in ("en", "pt")}
    print(f"split: {len(sp.train)} train / {len(sp.validation)} validation / {len(sp.test)} test "
          f"+ {len(golden)} golden (episode 8)   languages in train: {langs}")
    print(f"training tokens (about, {'tiktoken o200k_base' if tokens.exact() else 'chars/4 estimate'}): {t_tokens}; "
          f"system prompt: baseline {base_prompt} tokens vs short {short_prompt} tokens")
    if args.price_per_million is not None:
        c = economics.training_cost(t_tokens, args.epochs, args.price_per_million)
        print(f"estimated training cost for {args.epochs} epochs at {args.price_per_million}/M tokens: {c:.4f}")
    print("PREFLIGHT " + ("OK" if report.ok else "FAILED"))
    return 0 if report.ok else 1


def submit(args) -> int:
    client = jobs.make_client(args.endpoint)
    tr, va = jobs.upload(client, Path(args.out) / "training.jsonl"), jobs.upload(client, Path(args.out) / "validation.jsonl")
    rec = jobs.submit(client, args.model, tr, va, training_type=args.training_type, suffix=args.suffix,
                      n_epochs=args.epochs if args.epochs != "auto" else "auto")
    rec.save(Path(args.out) / "job.json")
    print(f"job {rec.job_id} submitted ({rec.training_type} training); a queued job is normal, don't resubmit")
    rec = jobs.wait(client, rec, poll_seconds=args.poll)
    rec.save(Path(args.out) / "job.json")
    print(f"fine-tuned model: {rec.fine_tuned_model}")
    rows = jobs.fetch_metrics(client, rec)
    if rows:
        last = rows[-1]
        print("last step:", {k: v for k, v in last.items() if v is not None})
        warn = jobs.overfit_signal(rows)
        print(warn or "no overfitting signal in the loss curves")
    return 0


def deploy_cmd(args) -> int:
    from . import deploy as dep
    rec = jobs.JobRecord.load(Path(args.out) / "job.json")
    token = dep.get_token()
    d = dep.deploy(token, args.subscription, args.resource_group, args.account, args.name,
                   args.model or rec.fine_tuned_model, sku=args.sku, capacity=args.capacity)
    print(f"deployment {args.name}: {d['properties']['provisioningState']} ({args.sku})")
    if args.sku != "DeveloperTier":
        print("NOTE: a Standard or Global Standard deployment of a fine-tuned model has an hourly hosting fee "
              "even when idle. Delete it when you are done.")
    return 0


def evaluate_cmd(args) -> int:
    client = jobs.make_client(args.endpoint)
    cases = [dataset.Example(d["id"], d["text"], d["category"], d.get("urgency"), d.get("needs_human"))
             for d in dataset.read_jsonl(Path(args.out) / "test.jsonl")]
    base = evaluate.run(client, args.base, baseline_system(), cases)
    tuned = evaluate.run(client, args.tuned, SHORT_SYSTEM, cases)
    cmp = evaluate.compare(base, tuned)
    print(evaluate.render(cmp))
    return 0 if cmp.promote else 1


def cleanup(args) -> int:
    from . import deploy as dep
    dep.delete(dep.get_token(), args.subscription, args.resource_group, args.account, args.name)
    print(f"deployment {args.name} deleted; the fine-tuned model remains (delete it in the portal, or delete the resource group)")
    if args.endpoint:
        rec = jobs.JobRecord.load(Path(args.out) / "job.json")
        client = jobs.make_client(args.endpoint)
        for fid in [rec.training_file, rec.validation_file, *rec.result_files]:
            client.files.delete(fid)
            print(f"file {fid} deleted")
    return 0


def cost(args) -> int:
    base = economics.Serving(args.base_prompt_tokens, args.completion_tokens, args.base_input_price,
                             args.base_output_price)
    tuned = economics.Serving(args.tuned_prompt_tokens, args.completion_tokens, args.tuned_input_price,
                              args.tuned_output_price, args.hosting_per_hour)
    n = economics.breakeven_calls_per_month(base, tuned, args.training_cost, args.amortise_months)
    print(f"per call: baseline {base.per_call():.6f}, tuned {tuned.per_call():.6f}")
    print("tuned model is never cheaper per call; it has to win on quality or latency" if n is None
          else f"break-even: {n:,.0f} calls per month (hosting + training over {args.amortise_months} months)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fttriage")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("prepare", help="split, build the JSONL files and run the pre-flight checks")
    a.add_argument("--labelled", default=str(DATA / "labelled.jsonl"))
    a.add_argument("--golden", default=str(DATA / "golden_ep08.jsonl"))
    a.add_argument("--out", default="build")
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--epochs", type=int, default=3, help="only for the cost estimate")
    a.add_argument("--price-per-million", type=float, default=None, help="training price per million tokens")
    a.set_defaults(fn=prepare)

    s = sub.add_parser("submit", help="upload the files, start the job, wait, print the metrics")
    s.add_argument("--endpoint", required=True)
    s.add_argument("--model", default="gpt-4.1-mini-2025-04-14")
    s.add_argument("--training-type", default="Standard", choices=jobs.TRAINING_TYPES)
    s.add_argument("--suffix", default="hr-triage")
    s.add_argument("--epochs", default="auto")
    s.add_argument("--out", default="build")
    s.add_argument("--poll", type=float, default=30)
    s.set_defaults(fn=submit)

    d = sub.add_parser("deploy", help="deploy the fine-tuned model (management REST API)")
    for x in (d,):
        x.add_argument("--subscription", required=True)
        x.add_argument("--resource-group", required=True)
        x.add_argument("--account", required=True)
        x.add_argument("--name", default="triage-ft")
    d.add_argument("--model", default=None, help="default: the model in build/job.json")
    d.add_argument("--sku", default="DeveloperTier", choices=("DeveloperTier", "Standard", "GlobalStandard"))
    d.add_argument("--capacity", type=int, default=50)
    d.add_argument("--out", default="build")
    d.set_defaults(fn=deploy_cmd)

    e = sub.add_parser("evaluate", help="base + long prompt vs tuned + short prompt on the held-out set")
    e.add_argument("--endpoint", required=True)
    e.add_argument("--base", default="base")
    e.add_argument("--tuned", default="triage-ft")
    e.add_argument("--out", default="build")
    e.set_defaults(fn=evaluate_cmd)

    c = sub.add_parser("cleanup", help="delete the fine-tuned deployment")
    c.add_argument("--subscription", required=True)
    c.add_argument("--resource-group", required=True)
    c.add_argument("--account", required=True)
    c.add_argument("--name", default="triage-ft")
    c.add_argument("--endpoint", default=None, help="also delete the uploaded training / validation / result files")
    c.add_argument("--out", default="build")
    c.set_defaults(fn=cleanup)

    k = sub.add_parser("cost", help="break-even calls per month (prices are arguments, from the pricing page)")
    for n in ("base-prompt-tokens", "tuned-prompt-tokens", "completion-tokens", "base-input-price", "base-output-price",
              "tuned-input-price", "tuned-output-price", "hosting-per-hour", "training-cost"):
        k.add_argument(f"--{n}", type=float, required=True)
    k.add_argument("--amortise-months", type=int, default=12)
    k.set_defaults(fn=cost)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
