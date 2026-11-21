"""Send a window of HR questions through the real triage deployment and record monitoring telemetry.

    PYTHONPATH=src python -m hrmon.traffic --data data/baseline.jsonl --window baseline \
        --aoai-endpoint $AOAI --deployment chat --appinsights "$APPINSIGHTS" [--golden data/golden.jsonl]

In production the window is a time range; for the demo two labelled windows are replayed back to back.
--local-out writes the same records to a JSON lines file (used by the tests and for offline analysis).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import telemetry
from .features import input_features
from .triage import make_openai_client, triage


def load(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def run_window(client, deployment: str, window: str, questions: list[dict], sink, pause: float = 0.0) -> int:
    failures = 0
    for q in questions:
        feats = input_features(q["question"])
        try:
            t = triage(client, deployment, q["question"])
        except Exception as e:                      # one bad call must not stop the window; it is recorded
            failures += 1
            sink("triage_error", telemetry.attributes(window, error=type(e).__name__, **feats))
            continue
        sink("triage", telemetry.attributes(
            window, **feats, category=t.category, urgency=t.urgency, needs_human=t.needs_human, model=t.model,
            latency_ms=t.latency_ms, prompt_tokens=t.prompt_tokens, completion_tokens=t.completion_tokens))
        if pause:
            time.sleep(pause)
    return failures


def run_golden(client, deployment: str, window: str, golden: list[dict], sink) -> float:
    """Quality signal: accuracy on a small labelled set, re-run in every window. Drift metrics say 'different';
    this says 'worse'."""
    correct = sum(triage(client, deployment, g["question"]).category == g["category"] for g in golden)
    accuracy = correct / len(golden)
    sink("quality", telemetry.attributes(window, golden_accuracy=round(accuracy, 4), golden_n=len(golden)))
    return accuracy


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data", required=True)
    p.add_argument("--window", required=True)
    p.add_argument("--aoai-endpoint", required=True)
    p.add_argument("--deployment", default="chat")
    p.add_argument("--golden")
    p.add_argument("--appinsights", help="Application Insights connection string (keyless ingestion)")
    p.add_argument("--local-out", help="also append records to this JSON lines file")
    p.add_argument("--pause", type=float, default=0.2)
    a = p.parse_args(argv)
    telemetry.check_window(a.window)

    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    if a.appinsights:
        telemetry.setup_azure_monitor(a.appinsights, cred)
    local = open(a.local_out, "a", encoding="utf-8") if a.local_out else None

    def sink(message: str, attrs: dict) -> None:
        telemetry.emit(message, attrs)
        if local:
            local.write(json.dumps({"message": message, **attrs}) + "\n")

    client = make_openai_client(a.aoai_endpoint, cred)
    questions = load(a.data)
    failures = run_window(client, a.deployment, a.window, questions, sink, a.pause)
    print(f"window {a.window}: {len(questions) - failures} triaged, {failures} failed")
    if a.golden:
        print(f"window {a.window}: golden accuracy {run_golden(client, a.deployment, a.window, load(a.golden), sink):.2f}")
    if local:
        local.close()
    telemetry.flush()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
