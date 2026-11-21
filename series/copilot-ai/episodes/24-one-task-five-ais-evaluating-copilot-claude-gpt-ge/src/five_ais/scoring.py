"""Deterministic checks. No LLM judge: each rule is a plain test you can read. A task without checks scores 0."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import sandbox


@dataclass
class CheckResult:
    rule: str
    passed: bool
    detail: str = ""


def extract_json(text: str) -> Any:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    body = (m.group(1) if m else text).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    for o, c in (("{", "}"), ("[", "]")):
        a, b = body.find(o), body.rfind(c)
        if a != -1 and b > a:
            try:
                return json.loads(body[a:b + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found")


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(re.sub(r"[^\d.,-]", "", v).replace(",", ""))
        except ValueError:
            return None
    return None


def numbers_in(text: str) -> list[float]:
    """Numbers as people write them: 19,803 or 19 803 or 19803.00 (a space or comma between digit groups of three)."""
    out = []
    for m in re.finditer(r"\d{1,3}(?:[ ,.  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", text):
        raw = m.group(0)
        for variant in ({re.sub(r"[ ,  ]", "", raw)}, {re.sub(r"[ .  ]", "", raw).replace(",", ".")}):
            try:
                out.append(float(variant.pop()))
            except ValueError:
                pass
    return out


def run_checks(answer: str, checks: dict, allow_exec: bool = False) -> list[CheckResult]:
    """Keys: contains_all, contains_any, not_contains, regex, not_regex, max_words, json_fields {key: expected},
    number_in_text, python_tests {function_name_hint, cases:[{call, expect}]}."""
    low, out = answer.lower(), []
    for s in checks.get("contains_all", []):
        out.append(CheckResult(f"contains_all:{s}", s.lower() in low))
    if checks.get("contains_any"):
        hit = [s for s in checks["contains_any"] if s.lower() in low]
        out.append(CheckResult("contains_any:" + "|".join(checks["contains_any"]), bool(hit), ",".join(hit)))
    for s in checks.get("not_contains", []):
        out.append(CheckResult(f"not_contains:{s}", s.lower() not in low))
    for pat in checks.get("regex", []):
        out.append(CheckResult(f"regex:{pat}", re.search(pat, answer, re.I | re.S) is not None))
    for pat in checks.get("not_regex", []):
        out.append(CheckResult(f"not_regex:{pat}", re.search(pat, answer, re.I | re.S) is None))
    if "max_words" in checks:
        n = len(answer.split())
        out.append(CheckResult(f"max_words:{checks['max_words']}", n <= checks["max_words"], f"{n} words"))
    if "json_fields" in checks:
        try:
            obj = extract_json(answer)
        except ValueError:
            obj = None
        for k, want in checks["json_fields"].items():
            got = obj.get(k) if isinstance(obj, dict) else None
            ok = obj is not None and ((abs(_num(got) - float(want)) < 0.005) if isinstance(want, (int, float))
                                      and not isinstance(want, bool) and _num(got) is not None else got == want)
            out.append(CheckResult(f"json_field:{k}={want}", ok, "no JSON" if obj is None else f"got {got!r}"))
    if "number_in_text" in checks:
        want = float(checks["number_in_text"])
        out.append(CheckResult(f"number_in_text:{checks['number_in_text']}", any(abs(n - want) < 0.005 for n in numbers_in(answer))))
    if "python_tests" in checks:
        if not allow_exec:
            out.append(CheckResult("python_tests", False, "skipped: code execution not allowed (--allow-code-exec)"))
        else:
            for r in sandbox.run_tests(sandbox.extract_code(answer), checks["python_tests"]["cases"]):
                out.append(CheckResult(f"python:{r['call']}", bool(r["ok"]), r["got"]))
    return out


def score(results: list[CheckResult]) -> float:
    return sum(r.passed for r in results) / len(results) if results else 0.0
