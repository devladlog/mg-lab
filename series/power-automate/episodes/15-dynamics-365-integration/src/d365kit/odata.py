"""OData filter text for Dataverse: build literals, check the text, and evaluate it against a row.

The checks come from Microsoft Learn (Filter rows by using OData; Use lists of rows in flows; Trigger flows when a row is
added, modified, or deleted). The evaluator is a small local stand-in so tests can prove which rows a filter lets through;
it is not the Dataverse query engine and knows only the operators listed in `evaluate_filter`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_CONDITIONS = 500  # Learn: "You can include up to 500 total conditions in a query"


class FilterError(ValueError):
    pass


@dataclass
class Finding:
    level: str  # "error" | "warning"
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code} {self.message}"


# ----------------------------------------------------------------------------------------------- building
def quote(text: str) -> str:
    """String literal: single quotes are doubled (Learn: lastname eq 'O''Bryan')."""
    return "'" + text.replace("'", "''") + "'"


def literal(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return quote(str(value))


def bind(entity_set: str, row_id: str) -> str:
    """Value of a lookup in 'Add a new row': <entity set name>(<item id>) (Learn: Use a flow to add a row in Dataverse)."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", entity_set):
        raise ValueError(f"{entity_set!r} doesn't look like an entity set name (lower case, e.g. opportunities)")
    if not GUID_RE.match(row_id):
        raise ValueError(f"{row_id!r} is not a GUID")
    return f"{entity_set}({row_id})"


# ----------------------------------------------------------------------------------------------- checking
def check_filter(text: str) -> list[Finding]:
    out: list[Finding] = []
    if "$filter=" in text.replace(" ", "").lower():
        out.append(Finding("error", "ODATA001", "the box takes the expression only: it can't contain '$filter=' "
                                                 "(Learn, List rows and trigger Filter rows)"))
    if text.count("'") % 2:
        out.append(Finding("error", "ODATA002", "odd number of single quotes: double the quote inside a value "
                                                 "('O''Bryan'), otherwise Dataverse reports an unterminated literal"))
    if text.count("(") != text.count(")"):
        out.append(Finding("error", "ODATA003", "unbalanced parentheses"))
    for m in re.finditer(r"(startswith|endswith)\(\s*[\w/]+\s*,\s*'([^']*)'\s*\)", text, re.I):
        fn, arg = m.group(1).lower(), m.group(2)
        if (fn == "startswith" and arg.startswith("%")) or (fn == "endswith" and arg.endswith("%")):
            out.append(Finding("warning", "ODATA004", f"leading wildcard in {m.group(0)}: not supported and slow "
                                                       "(Learn, Filter rows by using OData)"))
    if re.search(r"'[^']*[&#+][^']*'", text):
        out.append(Finding("warning", "ODATA005", "a literal contains &, # or +: URL-encode it (%26, %23, %2B) "
                                                   "(Learn, List rows > Filter rows)"))
    n = len(re.findall(r"\b(eq|ne|gt|ge|lt|le)\b|\b(contains|startswith|endswith)\(", text, re.I))
    if n > MAX_CONDITIONS:
        out.append(Finding("error", "ODATA006", f"{n} conditions; a query can have up to {MAX_CONDITIONS}"))
    return out


# ----------------------------------------------------------------------------------------------- evaluating
_TOKEN = re.compile(r"""\s*(?:
    (?P<str>'(?:[^']|'')*')
  | (?P<dt>\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)
  | (?P<date>\d{4}-\d{2}-\d{2})
  | (?P<guid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})
  | (?P<num>-?\d+(?:\.\d+)?)
  | (?P<word>[A-Za-z_][\w./]*)
  | (?P<sym>[(),])
)""", re.X)
_CMP = {"eq", "ne", "gt", "ge", "lt", "le"}


def _tokens(text: str):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise FilterError(f"can't read the filter at: {text[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def _to_dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


class _Parser:
    def __init__(self, text, row):
        self.t, self.i, self.row = _tokens(text), 0, row

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def word(self, w):
        k, v = self.peek()
        return k == "word" and v.lower() == w

    def parse(self):
        v = self.or_()
        if self.i != len(self.t):
            raise FilterError(f"unexpected {self.peek()[1]!r}")
        return bool(v)

    def or_(self):
        v = self.and_()
        while self.word("or"):
            self.take()
            r = self.and_()
            v = bool(v) or bool(r)
        return v

    def and_(self):
        v = self.not_()
        while self.word("and"):
            self.take()
            r = self.not_()
            v = bool(v) and bool(r)
        return v

    def not_(self):
        if self.word("not"):
            self.take()
            return not self.not_()
        return self.cmp_()

    def cmp_(self):
        left = self.primary()
        k, v = self.peek()
        if k == "word" and v.lower() in _CMP:
            op = self.take()[1].lower()
            return _compare(op, left, self.primary())
        return left

    def primary(self):
        k, v = self.take()
        if k == "sym" and v == "(":
            r = self.or_()
            if self.take() != ("sym", ")"):
                raise FilterError("missing ')'")
            return r
        if k == "str":
            return ("lit", v[1:-1].replace("''", "'"))
        if k == "num":
            return ("lit", float(v) if "." in v else int(v))
        if k in ("dt", "date", "guid"):
            return ("lit", v)
        if k == "word":
            low = v.lower()
            if low in ("true", "false"):
                return ("lit", low == "true")
            if low == "null":
                return ("lit", None)
            if self.peek() == ("sym", "("):
                return self.call(low)
            return ("col", v)
        raise FilterError(f"unexpected {v!r}")

    def call(self, fn):
        self.take()  # (
        args = [self.primary()]
        while self.peek() == ("sym", ","):
            self.take()
            args.append(self.primary())
        if self.take() != ("sym", ")"):
            raise FilterError("missing ')'")
        if fn not in ("contains", "startswith", "endswith") or len(args) != 2:
            raise FilterError(f"the function {fn}() isn't supported by this evaluator")
        a, b = (str(self.val(x) or "").lower() for x in args)
        return {"contains": b in a, "startswith": a.startswith(b), "endswith": a.endswith(b)}[fn]

    def val(self, node):
        if isinstance(node, bool):
            return node
        kind, v = node
        if kind == "lit":
            return v
        cur = self.row
        for part in v.split("/"):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur


def _compare(op, l, r):
    p = _CURRENT
    a, b = p.val(l), p.val(r)
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        res = {"eq": a == b, "ne": a != b}.get(op)
        if res is None:
            return False
        return res
    da, db = _to_dt(a), _to_dt(b)
    if da is not None and db is not None and not (isinstance(a, (int, float)) or isinstance(b, (int, float))):
        a, b = da, db
    elif isinstance(a, str) and isinstance(b, str):
        a, b = a.lower(), b.lower()  # Learn: filters on string values are case insensitive
    elif isinstance(a, (int, float)) != isinstance(b, (int, float)):
        return op == "ne"
    return {"eq": a == b, "ne": a != b, "gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[op]


_CURRENT: _Parser  # set by evaluate_filter (single-threaded helper)


def evaluate_filter(text: str, row: dict) -> bool:
    """True when the row passes the filter. Supports eq ne gt ge lt le, and or not, parentheses, contains,
    startswith, endswith, string / number / boolean / null / date / datetime / GUID literals and lookup/column paths."""
    global _CURRENT
    _CURRENT = _Parser(text, row)
    return _CURRENT.parse()
