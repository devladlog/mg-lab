"""Deterministic checks for a model answer. No LLM judge: every rule is a plain test you can read."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    rule: str
    passed: bool
    detail: str = ""


def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()


def extract_json(text: str) -> Any:
    """Parse the first JSON object or array in the text (models often add a fence or a sentence around it)."""
    body = _strip_fence(text)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = body.find(opener), body.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(body[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found")


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.,-]", "", value).replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def run_checks(answer: str, checks: dict) -> list[CheckResult]:
    """checks keys: contains_all, contains_any, not_contains, regex, max_words, json_fields {path: expected}, number_in_text."""
    low = answer.lower()
    out: list[CheckResult] = []
    for s in checks.get("contains_all", []):
        out.append(CheckResult(f"contains_all:{s}", s.lower() in low))
    if checks.get("contains_any"):
        hit = [s for s in checks["contains_any"] if s.lower() in low]
        out.append(CheckResult("contains_any:" + "|".join(checks["contains_any"]), bool(hit), ",".join(hit)))
    for s in checks.get("not_contains", []):
        out.append(CheckResult(f"not_contains:{s}", s.lower() not in low))
    for pat in checks.get("regex", []):
        out.append(CheckResult(f"regex:{pat}", re.search(pat, answer, re.I | re.S) is not None))
    if "max_words" in checks:
        n = len(answer.split())
        out.append(CheckResult(f"max_words:{checks['max_words']}", n <= checks["max_words"], f"{n} words"))
    if "number_in_text" in checks:
        want = float(checks["number_in_text"])
        found = [_num(tok) for tok in re.findall(r"\d[\d.,\s]*\d|\d", answer)]
        out.append(CheckResult(f"number_in_text:{want:g}", any(f is not None and abs(f - want) < 0.5 for f in found)))
    if "json_fields" in checks:
        try:
            data = extract_json(answer)
        except ValueError:
            out.append(CheckResult("json_valid", False, "no JSON in answer"))
            return out
        out.append(CheckResult("json_valid", True))
        for path, expected in checks["json_fields"].items():
            cur: Any = data
            try:
                for part in path.split("."):
                    cur = cur[int(part)] if isinstance(cur, list) else cur[part]
            except (KeyError, IndexError, ValueError, TypeError):
                out.append(CheckResult(f"json:{path}", False, "missing"))
                continue
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                ok = _num(cur) is not None and abs(_num(cur) - expected) < 0.5
            else:
                ok = str(cur).strip().lower() == str(expected).strip().lower()
            out.append(CheckResult(f"json:{path}", ok, f"got {cur!r}"))
    return out


def score(answer: str, checks: dict) -> tuple[float, list[CheckResult]]:
    results = run_checks(answer, checks)
    if not results:
        return 0.0, results
    return sum(r.passed for r in results) / len(results), results
