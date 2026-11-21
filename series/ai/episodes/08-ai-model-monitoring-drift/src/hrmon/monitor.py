"""Drift monitor: baseline window vs current window -> drift per feature, quality, model version, exit code.

    PYTHONPATH=src python -m hrmon.monitor --workspace-id $WS --baseline baseline --current current \
        [--appinsights "$APPINSIGHTS"]          # also emits a drift_report record for the alert rule
    PYTHONPATH=src python -m hrmon.monitor --local records.jsonl --baseline baseline --current current

Exit 0 = no significant drift and no quality drop; 1 = investigate (a pipeline or scheduler can act on it).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from . import drift, telemetry
from .logs import FEATURES, fetch

P = telemetry.PREFIX
INPUT_FEATURES = ["lang", "length"]                     # data drift
OUTPUT_FEATURES = ["category", "urgency", "needs_human"]  # prediction drift
QUALITY_DROP = 0.10                                     # golden accuracy may fall at most 10 points


@dataclass
class Report:
    features: list[drift.FeatureDrift] = field(default_factory=list)
    models: dict[str, list[str]] = field(default_factory=dict)
    quality: dict[str, float] = field(default_factory=dict)

    @property
    def model_changed(self) -> bool:
        b, c = (set(v) for v in self.models.values()) if len(self.models) == 2 else (set(), set())
        return bool(b and c and b != c)

    @property
    def quality_dropped(self) -> bool:
        vals = list(self.quality.values())
        return len(vals) == 2 and vals[0] - vals[1] > QUALITY_DROP

    @property
    def alert(self) -> bool:
        return any(f.drifted for f in self.features) or self.quality_dropped or self.model_changed

    @property
    def max_psi(self) -> float:
        return max((f.psi for f in self.features if f.psi is not None), default=0.0)


def analyse(records: list[dict], baseline: str, current: str) -> Report:
    rep = Report()
    triage = {w: [r for r in records if r.get("message") == "triage" and r.get(f"{P}window") == w]
              for w in (baseline, current)}
    for f in INPUT_FEATURES + OUTPUT_FEATURES:
        rep.features.append(drift.compare(f, [str(r.get(f"{P}{f}")) for r in triage[baseline]],
                                          [str(r.get(f"{P}{f}")) for r in triage[current]]))
    for w in (baseline, current):
        rep.models[w] = sorted({str(r.get(f"{P}model")) for r in triage[w]})
        q = [r[f"{P}golden_accuracy"] for r in records
             if r.get("message") == "quality" and r.get(f"{P}window") == w and r.get(f"{P}golden_accuracy") is not None]
        if q:
            rep.quality[w] = float(q[-1])                    # latest quality run in that window
    return rep


def render(rep: Report, baseline: str, current: str) -> str:
    lines = [f"Drift report: {baseline} -> {current}", "",
             f"{'feature':<12} {'kind':<11} {'n':>9} {'PSI':>7} {'JS':>6}  status        biggest shift"]
    for f in rep.features:
        kind = "input" if f.feature in INPUT_FEATURES else "prediction"
        n = f"{f.n_baseline}/{f.n_current}"
        psi_s = f"{f.psi:7.3f}" if f.psi is not None else "      -"
        js_s = f"{f.js:6.3f}" if f.js is not None else "     -"
        shift = ", ".join(f"{v} {b:.0%}->{c:.0%}" for v, b, c in f.shifts[:2])
        lines.append(f"{f.feature:<12} {kind:<11} {n:>9} {psi_s} {js_s}  {f.status:<13} {shift}")
    lines.append("")
    lines.append("model versions: " + "; ".join(f"{w}: {', '.join(m) or '-'}" for w, m in rep.models.items())
                 + ("  << CHANGED" if rep.model_changed else ""))
    if rep.quality:
        lines.append("golden accuracy: " + "; ".join(f"{w}: {v:.2f}" for w, v in rep.quality.items())
                     + ("  << DROPPED" if rep.quality_dropped else ""))
    lines += ["", f"ALERT: {'YES' if rep.alert else 'no'}  (max PSI {rep.max_psi:.3f}; "
                  f"significant >= {drift.PSI_SIGNIFICANT})"]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--baseline", required=True)
    p.add_argument("--current", required=True)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--workspace-id", help="Log Analytics workspace ID (GUID)")
    src.add_argument("--local", help="JSON lines records written by traffic --local-out")
    p.add_argument("--lookback-hours", type=int, default=24)
    p.add_argument("--appinsights", help="emit a drift_report record (the alert rule reads it)")
    a = p.parse_args(argv)

    if a.local:
        records = [json.loads(x) for x in Path(a.local).read_text(encoding="utf-8").splitlines() if x.strip()]
        cred = None
    else:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import LogsQueryClient
        cred = DefaultAzureCredential()
        records = fetch(LogsQueryClient(cred), a.workspace_id, [a.baseline, a.current],
                        timedelta(hours=a.lookback_hours))
    rep = analyse(records, a.baseline, a.current)
    print(render(rep, a.baseline, a.current))

    if a.appinsights:
        if cred is None:
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
        telemetry.setup_azure_monitor(a.appinsights, cred)
        telemetry.emit("drift_report", telemetry.attributes(
            a.current, baseline=a.baseline, max_psi=round(rep.max_psi, 4), alert=rep.alert,
            drifted=",".join(f.feature for f in rep.features if f.drifted), model_changed=rep.model_changed,
            quality_dropped=rep.quality_dropped))
        telemetry.flush()
    return 1 if rep.alert else 0


if __name__ == "__main__":
    sys.exit(main())
