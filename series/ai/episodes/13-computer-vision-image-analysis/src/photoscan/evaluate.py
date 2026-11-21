"""The gate. Safety first: a wrong asset tag must never be attached, a detected person must really be pixelated,
no call may fail. Then a modest read-rate threshold. All expectations are ours, written in data/cases.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import samples
from .model import VisionBackend
from .pipeline import Result, process
from .privacy import region_changed

MIN_TAG_READ_RATE = 0.60
ATTACHING = {"attach-to-asset", "attach-then-review"}


@dataclass
class Row:
    id: str
    decision: str = ""
    expected_decision: str | None = None
    tag_read: str | None = None
    expected_tag: str | None = None
    people_blurred: int = 0
    problems: list[str] = field(default_factory=list)
    skipped: bool = False


@dataclass
class Report:
    rows: list[Row]
    tag_read_rate: float
    wrong_tag_attached: int
    failed: int
    people_failures: int
    passed: bool
    messages: list[str]


def _load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text())["cases"]


def evaluate(backend: VisionBackend, cases_path: Path, sample_dir: Path, skip_people: bool = False) -> Report:
    gen = samples.generate()
    rows: list[Row] = []
    wrong = failed = people_fail = 0
    expecting = reading = 0
    msgs: list[str] = []
    for c in _load_cases(cases_path):
        row = Row(c["id"], expected_decision=c.get("decision"), expected_tag=c.get("tag"))
        if c["source"] == "generate":
            raw = gen[c["id"]]
        else:
            p = sample_dir / "learn-presentation.png"
            if not p.exists():
                row.skipped = True
                if skip_people:
                    row.problems.append("skipped (--skip-people)")
                else:
                    row.problems.append("photo not downloaded: run `python -m photoscan fetch-sample`")
                    people_fail += 1
                rows.append(row)
                continue
            raw = p.read_bytes()
        r: Result = process(raw, backend, c["id"])
        row.decision = r.decision
        row.tag_read = r.tags[0].tag if r.tags else None
        row.people_blurred = len(r.blurred)
        if r.error:
            failed += 1
            row.problems.append(r.error)
        if c.get("tag"):
            expecting += 1
            if row.tag_read == c["tag"]:
                reading += 1
            else:
                row.problems.append(f"expected {c['tag']}, read {row.tag_read}")
        if r.decision in ATTACHING and row.tag_read != c.get("tag"):
            wrong += 1
            row.problems.append(f"WRONG TAG ATTACHED: {row.tag_read}")
        pm = c.get("people_min")
        if pm:
            if row.people_blurred < pm:
                people_fail += 1
                row.problems.append(f"expected at least {pm} person blurred, got {row.people_blurred}")
            for b in r.blurred:
                if not region_changed(r.prepared_png, r.redacted_png, b):
                    people_fail += 1
                    row.problems.append("a box was reported blurred but its pixels did not change")
        rows.append(row)
    rate = reading / expecting if expecting else 1.0
    ok = failed == 0 and wrong == 0 and people_fail == 0 and rate >= MIN_TAG_READ_RATE
    if rate < MIN_TAG_READ_RATE:
        msgs.append(f"tag read rate {rate:.0%} < {MIN_TAG_READ_RATE:.0%}")
    return Report(rows, rate, wrong, failed, people_fail, ok, msgs)


def render(rep: Report) -> str:
    out = [f"{'case':22} {'decision':20} {'expected':18} {'tag read':11} blurred", "-" * 84]
    for r in rep.rows:
        out.append(f"{r.id:22} {r.decision or '-':20} {r.expected_decision or '-':18} {r.tag_read or '-':11} {r.people_blurred}")
        for p in r.problems:
            out.append(f"    ! {p}")
    out += ["", f"tag read rate: {rep.tag_read_rate:.0%}   wrong tags attached: {rep.wrong_tag_attached}   "
                f"failed calls: {rep.failed}   people checks failed: {rep.people_failures}"]
    out += [f"  {m}" for m in rep.messages]
    out.append("RESULT: " + ("PASS" if rep.passed else "FAIL"))
    return "\n".join(out)
