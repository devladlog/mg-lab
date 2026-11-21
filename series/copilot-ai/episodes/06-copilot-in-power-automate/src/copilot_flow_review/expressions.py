"""Static check of an expression, for the ones Copilot's expression assistant (or anyone) writes.

This is NOT an evaluator. It catches what can be known without running the flow:
unbalanced brackets, unterminated strings, function names that are not in the Learn function list,
and date format strings that use letters that are not .NET format specifiers.
Run the expression in the flow (Compose + test run) to see its value: that is the only real evaluation.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .findings import Finding

DATA = Path(__file__).resolve().parents[1] / "data" / "wdl-functions.txt"

# Position (0-based) of the optional format argument, from the function signatures on Learn.
FORMAT_ARG = {"formatdatetime": 1, "converttimezone": 3, "convertfromutc": 2, "converttoutc": 2, "getfuturetime": 2,
              "getpasttime": 2, "addtotime": 3, "adddays": 2, "addhours": 2, "addminutes": 2, "addseconds": 2}


@lru_cache(maxsize=1)
def known_functions() -> dict[str, str]:
    """lower-case name -> documented spelling"""
    names = [l.strip() for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return {n.lower(): n for n in names}


def strip_wrapper(text: str) -> str:
    """Accept '@concat(...)' and '@{concat(...)}' as well as the bare expression."""
    t = text.strip()
    if t.startswith("@{") and t.endswith("}"):
        return t[2:-1]
    if t.startswith("@") and not t.startswith("@@"):
        return t[1:]
    return t


def check_expression(text: str, where: str = "expression") -> list[Finding]:
    expr = strip_wrapper(text)
    findings: list[Finding] = []
    tokens, error = _tokenize(expr)
    if error:
        findings.append(Finding("EX001", "error", where, error))
        return findings

    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for kind, value, pos in tokens:
        if kind == "punct" and value in "([{":
            stack.append((value, pos))
        elif kind == "punct" and value in ")]}":
            if not stack or stack[-1][0] != pairs[value]:
                findings.append(Finding("EX001", "error", where, f"Unexpected '{value}' at position {pos}."))
                return findings
            stack.pop()
    if stack:
        opener, pos = stack[-1]
        findings.append(Finding("EX001", "error", where, f"'{opener}' at position {pos} is never closed."))
        return findings

    known = known_functions()
    for i, (kind, value, pos) in enumerate(tokens):
        if kind == "name" and i + 1 < len(tokens) and tokens[i + 1][1] == "(":
            documented = known.get(value.lower())
            if documented is None:
                findings.append(Finding("EX002", "error", where,
                    f"'{value}' is not in the function list on Microsoft Learn (workflow definition language)."))
            elif documented != value:
                findings.append(Finding("EX002", "info", where,
                    f"'{value}' is spelled '{documented}' on Learn."))
            if value.lower() in FORMAT_ARG:
                findings.extend(_format_findings(tokens, i, where))
    return findings


def _tokenize(expr: str):
    tokens = []
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
        elif c == "'":
            j = i + 1
            while j < n:
                if expr[j] == "'":
                    if j + 1 < n and expr[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            else:
                return tokens, f"The string that starts at position {i} is never closed (a single quote is missing)."
            tokens.append(("string", expr[i + 1:j].replace("''", "'"), i))
            i = j + 1
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(("name", expr[i:j], i))
            i = j
        elif c.isdigit():
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(("number", expr[i:j], i))
            i = j
        else:
            tokens.append(("punct", c, i))
            i += 1
    return tokens, None


def _format_findings(tokens, call_index: int, where: str) -> list[Finding]:
    """The format argument of a date function is a custom .NET pattern (Learn, formatDateTime): check it if it is a literal."""
    position = FORMAT_ARG[tokens[call_index][1].lower()]
    args: list[list] = [[]]
    depth = 0
    for kind, value, pos in tokens[call_index + 1:]:
        if kind == "punct" and value in "([{":
            depth += 1
            if depth == 1:
                continue
        elif kind == "punct" and value in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif kind == "punct" and value == "," and depth == 1:
            args.append([])
            continue
        args[-1].append((kind, value, pos))
    if position < len(args) and len(args[position]) == 1 and args[position][0][0] == "string":
        return check_date_format(args[position][0][1], where)
    return []


def check_date_format(pattern: str, where: str = "format") -> list[Finding]:
    """Custom .NET date pattern problems that return wrong text instead of an error."""
    findings: list[Finding] = []
    if len(pattern) == 1:
        return findings  # a single character is a standard format specifier (for example 'o' or 'D')
    literal = pattern.replace("'", "")
    # Learn, "Custom date and time format strings": d, f, F, g, h, H, K, m, M, s, t, y, z, : and / are specifiers.
    # D, Y and S are not, so they are copied into the result as letters.
    wrong = sorted({ch for ch in literal if ch in "DYS"})
    if wrong:
        hint = {"D": "dd (day)", "Y": "yyyy (year)", "S": "ss (seconds)"}
        findings.append(Finding("EX003", "warning", where,
            f"Pattern '{pattern}': {', '.join(wrong)} is not a .NET custom format specifier, so it is copied into the result as a literal letter. "
            "Use " + ", ".join(hint[w] for w in wrong) + "."))
    if re.search(r"(yyyy|yy)[-/. ]mm|mm[-/. ](dd|yyyy|yy)", pattern):
        findings.append(Finding("EX004", "warning", where,
            f"Pattern '{pattern}': lowercase mm is minutes. The month is MM."))
    return findings
