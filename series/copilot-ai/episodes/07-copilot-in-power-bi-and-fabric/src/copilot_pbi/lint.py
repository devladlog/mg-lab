"""Copilot-readiness rules for a semantic model, plus AI instructions and verified-answer plans.

Every rule cites the Microsoft Learn statement it rests on (see README "References"). Severity:
  error   Copilot will not use it, or the limit is documented: fix before publishing
  warning documented guidance that changes answer quality
  info    judgement call, listed so a human decides
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from .tmdl import Model

# Limits documented on Learn (AI instructions article, verified-answers article, DAX/Copilot article)
AI_INSTRUCTIONS_MAX_CHARS = 10_000
DESCRIPTION_USED_CHARS = 200
VERIFIED_ANSWERS_MAX = 250
VERIFIED_TRIGGERS_MAX = 15
VERIFIED_TRIGGER_MAX_CHARS = 500


@dataclass
class Finding:
    rule: str
    severity: str
    where: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


_ABBREV = re.compile(r"(?:^|[ _])(cust|prod|amt|qty|nbr|num|cd|desc|ctry|dt|flg|fld|val)(?:$|[ _])", re.I)
_CAMEL = re.compile(r"[a-z][A-Z]")
_TRAILING_DIGIT = re.compile(r"[A-Za-z]\d+$")
_KEYLIKE = re.compile(r"(?:^|[\s_])(?:key|id)$", re.I)
_KEYLIKE_CAMEL = re.compile(r"[a-z](?:Key|ID|Id)$")


def cryptic(name: str) -> str | None:
    """Why a name is hard for a person or an LLM to read, or None. Learn: ProdID -> Product ID, CustNo -> Customer Number."""
    if len(name) < 3:
        return "shorter than three characters"
    if "_" in name:
        return "contains an underscore (technical name)"
    if _ABBREV.search(name):
        return "contains an abbreviation"
    if _CAMEL.search(name) and " " not in name:
        return "CamelCase without spaces"
    if _TRAILING_DIGIT.search(name):
        return "ends with a number (Col1, Field2)"
    return None


def lint_model(model: Model) -> list[Finding]:
    out: list[Finding] = []
    for t in model.tables:
        if t.hidden:
            continue
        if not t.description.strip():
            out.append(Finding("C002", "warning", f"table {t.name}",
                               "no description: say what one row is (the level of detail) and when to use the table"))
        for m in t.measures:
            where = f"measure [{m.name}]"
            if m.hidden:
                continue
            if not m.description.strip():
                out.append(Finding("C001", "warning", where,
                                   "no description: Copilot reads measure descriptions when it writes DAX"))
            if not m.format_string.strip():
                out.append(Finding("C007", "info", where, "no format string: unit and scale are unclear (currency, percent, count)"))
            why = cryptic(m.name)
            if why:
                out.append(Finding("C004", "warning", where, f"name is hard to read: {why}"))
        for c in t.columns:
            where = f"column {t.name}[{c.name}]"
            if c.hidden:
                continue
            if _KEYLIKE.search(c.name) or _KEYLIKE_CAMEL.search(c.name):
                out.append(Finding("C005", "warning", where,
                                   "key-like column is visible: hide it, hidden fields are excluded from what Copilot sees"))
            why = cryptic(c.name)
            if why:
                out.append(Finding("C004", "warning", where, f"name is hard to read: {why}"))
            if c.data_type in ("int64", "decimal", "double") and c.summarize_by not in ("none", "") and not c.is_key:
                out.append(Finding("C006", "info", where,
                                   f"numeric column summarises by {c.summarize_by}: define a measure and hide the column"))
        for m in t.measures:
            if len(m.description) > DESCRIPTION_USED_CHARS and not m.hidden:
                out.append(Finding("C003", "warning", f"measure [{m.name}]",
                                   f"description is {len(m.description)} characters; only the first {DESCRIPTION_USED_CHARS} are used"))
        for c in t.columns:
            if len(c.description) > DESCRIPTION_USED_CHARS and not c.hidden:
                out.append(Finding("C003", "warning", f"column {t.name}[{c.name}]",
                                   f"description is {len(c.description)} characters; only the first {DESCRIPTION_USED_CHARS} are used"))
        if len(t.description) > DESCRIPTION_USED_CHARS:
            out.append(Finding("C003", "warning", f"table {t.name}",
                               f"description is {len(t.description)} characters; only the first {DESCRIPTION_USED_CHARS} are used"))
    # same visible column name in more than one table: which one does 'sales by country' mean?
    seen: dict[str, list[tuple[str, bool]]] = {}
    names: dict[str, str] = {}
    for t in model.tables:
        for c in t.columns:
            if not c.hidden and not t.hidden:
                seen.setdefault(c.name.lower(), []).append((t.name, bool(c.description.strip())))
                names.setdefault(c.name.lower(), c.name)
    for name, homes in sorted(seen.items()):
        tables = sorted({h[0] for h in homes})
        if len(tables) > 1 and not all(h[1] for h in homes):
            out.append(Finding("C009", "warning", f"column {names[name]}",
                               f"the same name exists in {', '.join(tables)} and not every copy has a description that says which one is meant"))
    if not model.discourage_implicit_measures:
        out.append(Finding("C010", "info", "model",
                           "implicit measures are allowed: users and Copilot can aggregate any numeric column"))
    return out


_REF_TABLE_COL = re.compile(r"""(?:'([^']+)'|\b([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]""")
_REF_BARE = re.compile(r"(?<![A-Za-z0-9_'])\[([^\]]+)\]")


def lint_instructions(model: Model, text: str) -> list[Finding]:
    out: list[Finding] = []
    n = len(text)
    if not text.strip():
        return [Finding("A001", "error", "instructions", "no AI instructions text")]
    if n > AI_INSTRUCTIONS_MAX_CHARS:
        out.append(Finding("A002", "error", "instructions",
                           f"{n} characters; Learn limits AI instructions to {AI_INSTRUCTIONS_MAX_CHARS}"))
    spans = []
    for m in _REF_TABLE_COL.finditer(text):
        table = m.group(1) or m.group(2)
        item = m.group(3)
        spans.append((m.start(), m.end()))
        t = model.table(table)
        if t is None:
            out.append(Finding("A003", "error", f"{table}[{item}]", "table not found in the model"))
            continue
        hit = next((c for c in t.columns if c.name.lower() == item.lower()), None) \
            or next((x for x in t.measures if x.name.lower() == item.lower()), None)
        if hit is None:
            out.append(Finding("A003", "error", f"'{table}'[{item}]", "no such column or measure in that table"))
        elif hit.hidden:
            out.append(Finding("A004", "warning", f"'{table}'[{item}]",
                               "object is hidden: hidden fields are excluded from what Copilot sees for data questions"))
    for m in _REF_BARE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        item = m.group(1)
        hit = next((x for x in model.measures() if x.name.lower() == item.lower()), None) \
            or next((c for c in model.columns() if c.name.lower() == item.lower()), None)
        if hit is None:
            out.append(Finding("A003", "error", f"[{item}]", "no measure or column with this name in the model"))
        elif hit.hidden:
            out.append(Finding("A004", "warning", f"[{item}]",
                               "object is hidden: hidden fields are excluded from what Copilot sees for data questions"))
    return out


def lint_verified(plan: dict) -> list[Finding]:
    """Check a verified-answers *plan* (our own JSON format, not a Microsoft file) against the documented limits."""
    out: list[Finding] = []
    answers = plan.get("verifiedAnswers", [])
    if len(answers) > VERIFIED_ANSWERS_MAX:
        out.append(Finding("V001", "error", "plan", f"{len(answers)} verified answers; limit is {VERIFIED_ANSWERS_MAX} per model"))
    owners: dict[str, str] = {}
    for a in answers:
        name = a.get("visual", "?")
        phrases = a.get("triggerPhrases", [])
        if not phrases:
            out.append(Finding("V005", "error", name, "no trigger phrase"))
        if len(phrases) > VERIFIED_TRIGGERS_MAX:
            out.append(Finding("V002", "error", name, f"{len(phrases)} trigger phrases; limit is {VERIFIED_TRIGGERS_MAX} per verified answer"))
        for p in phrases:
            if len(p) > VERIFIED_TRIGGER_MAX_CHARS:
                out.append(Finding("V003", "error", name, f"a trigger phrase has {len(p)} characters; limit is {VERIFIED_TRIGGER_MAX_CHARS}"))
            key = " ".join(p.lower().split())
            if key in owners and owners[key] != name:
                out.append(Finding("V004", "warning", name,
                                   f"trigger phrase '{p}' is also used by '{owners[key]}': Copilot cannot tell them apart"))
            owners.setdefault(key, name)
    return out


def load_plan(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarise(findings: list[Finding]) -> dict[str, int]:
    s = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        s[f.severity] += 1
    return s
