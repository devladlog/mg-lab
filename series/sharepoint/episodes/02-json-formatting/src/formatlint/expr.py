"""Parse and evaluate SharePoint list-formatting expressions, locally.

* parse_excel("=if(@currentField > 5, 'a', 'b')") turns an Excel-style expression into the Abstract Syntax Tree
  form documented on Microsoft Learn ({"operator": "?", "operands": [...]}), so both syntaxes share one evaluator.
* evaluate(ast, ctx) computes the value for one row.

This is a test harness for the subset of the language our formats use, not a SharePoint renderer. Known
differences: dates are UTC, toLocale*() always formats as en-US, and a field that isn't in the row raises
FieldNotInView instead of rendering empty, because that is exactly the mistake we want tests to catch.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Operators listed in the formatting syntax reference on Microsoft Learn (AST names).
KNOWN_OPERATORS = {
    "+", "-", "/", "*", "<", ">", "%", "==", "!=", "<=", ">=", "||", "&&", "?", ":",
    "toString()", "Number()", "Date()", "cos", "sin", "toDateString()", "toLocaleString()",
    "toLocaleDateString()", "toLocaleTimeString()", "indexOf", "toLowerCase", "join", "length", "abs",
    "loopIndex", "floor", "ceiling", "pow", "substring", "getDate", "getMonth", "getYear", "toUpperCase",
    "lastIndexOf", "startsWith", "endsWith", "replace", "replaceAll", "padStart", "padEnd",
    "getThumbnailImage", "getUserImage", "addDays", "addMinutes", "appendTo", "removeFrom", "split",
}

# Excel-style function name -> AST operator name.
FUNCTION_ALIASES = {
    "if": "?", "Number": "Number()", "toString": "toString()", "Date": "Date()",
    "toDateString": "toDateString()", "toLocaleString": "toLocaleString()",
    "toLocaleDateString": "toLocaleDateString()", "toLocaleTimeString": "toLocaleTimeString()",
}

DAY_MS = 86_400_000


class FormatError(Exception):
    """Expression can't be parsed or uses something unknown."""


class NotSupportedLocally(FormatError):
    """Valid in SharePoint, but this local evaluator doesn't implement it."""


class FieldNotInView(FormatError):
    """[$Field] (or @currentField) isn't among the row's fields: in SharePoint it must be in the same view."""

    def __init__(self, name: str):
        super().__init__(f"field '{name}' is not in the view")
        self.name = name


# ---- tokenizer / parser ---------------------------------------------------------------------------------------

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<field>\[[$!][A-Za-z_][\w]*(?:\.[\w]+)*\])
  | (?P<special>@[A-Za-z_][\w]*(?:\.[\w]+)*)
  | (?P<name>[A-Za-z_][\w]*)
  | (?P<op>==|!=|<=|>=|&&|\|\||[-+*/%<>(),])
""", re.VERBOSE)

_BINARY = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, ">": 4, "<=": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}


def _tokenize(text: str):
    pos, out = 0, []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise FormatError(f"unexpected character {text[pos]!r} at {pos} in {text!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        val = m.group(kind)
        if kind == "num":
            val = float(val) if "." in val else int(val)
        elif kind == "str":
            val = re.sub(r"\\(.)", r"\1", val[1:-1])
        out.append((kind, val))
    return out


class _Parser:
    def __init__(self, tokens, source):
        self.t, self.i, self.src = tokens, 0, source

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise FormatError(f"expected {value or 'a value'} in {self.src!r}")
        self.i += 1
        return tok

    def expression(self, min_prec=1):
        left = self.unary()
        while True:
            kind, val = self.peek()
            if kind != "op" or val not in _BINARY or _BINARY[val] < min_prec:
                return left
            self.take()
            right = self.expression(_BINARY[val] + 1)
            left = {"operator": val, "operands": [left, right]}

    def unary(self):
        kind, val = self.peek()
        if kind == "op" and val == "-":
            self.take()
            operand = self.unary()
            if isinstance(operand, (int, float)):
                return -operand
            return {"operator": "*", "operands": [-1, operand]}
        return self.primary()

    def primary(self):
        kind, val = self.take()
        if kind in ("num", "str", "field", "special"):
            return val
        if kind == "name":
            if val in ("true", "false"):
                return val == "true"
            if self.peek() != ("op", "("):
                raise FormatError(f"unknown name {val!r} in {self.src!r}")
            self.take("(")
            args = []
            if self.peek() != ("op", ")"):
                args.append(self.expression())
                while self.peek() == ("op", ","):
                    self.take(",")
                    args.append(self.expression())
            self.take(")")
            op = FUNCTION_ALIASES.get(val, val)
            if op not in KNOWN_OPERATORS:
                raise FormatError(f"unknown function {val}() in {self.src!r}")
            return {"operator": op, "operands": args}
        if (kind, val) == ("op", "("):
            inner = self.expression()
            self.take(")")
            return inner
        raise FormatError(f"unexpected {val!r} in {self.src!r}")


def parse_excel(text: str):
    """'=...' Excel-style expression -> AST (dicts, strings, numbers, booleans)."""
    if not text.startswith("="):
        raise FormatError("Excel-style expressions start with '='")
    p = _Parser(_tokenize(text[1:]), text)
    ast = p.expression()
    if p.peek()[0] is not None:
        raise FormatError(f"unexpected {p.peek()[1]!r} after the end of {text!r}")
    return ast


def to_ast(value):
    """Any formatter value (Excel string, AST dict, plain string, number) -> AST."""
    if isinstance(value, str) and value.startswith("="):
        return parse_excel(value)
    if isinstance(value, dict) and "operator" in value:
        op = value["operator"]
        if op not in KNOWN_OPERATORS:
            raise FormatError(f"unknown operator {op!r}")
        return {"operator": op, "operands": [to_ast(o) for o in value.get("operands", [])]}
    return value


def field_refs(ast) -> set[str]:
    """Field names an AST reads: '[$Name...]' -> Name, '@currentField...' -> '@currentField'."""
    refs: set[str] = set()
    if isinstance(ast, dict):
        for o in ast.get("operands", []):
            refs |= field_refs(o)
    elif isinstance(ast, str):
        m = re.fullmatch(r"\[\$([A-Za-z_]\w*)(?:\.[\w.]+)?\]", ast)
        if m:
            refs.add(m.group(1))
        elif re.fullmatch(r"@currentField(?:\.[\w.]+)?", ast):
            refs.add("@currentField")
    return refs


# ---- evaluation -----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Date:
    ms: int  # milliseconds since 1970-01-01 UTC, like a JavaScript Date

    @staticmethod
    def parse(text: str) -> "Date":
        text = text.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                return Date(int(dt.timestamp() * 1000))
            except ValueError:
                pass
        raise FormatError(f"can't parse date {text!r}")

    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.ms / 1000, tz=timezone.utc)


@dataclass
class Context:
    row: dict                      # internal name -> value; only the fields that are in the view
    current_field: str | None = None
    me: str = ""
    now: Date = field(default_factory=lambda: Date(0))
    row_index: int = 0
    display: dict = field(default_factory=dict)   # internal name -> default-rendered text (displayValue)


def _num(v):
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Date):
        return v.ms
    if v is None or v == "":
        return 0
    if isinstance(v, str):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return math.nan
    return math.nan


def to_string(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, float):
        return repr(round(v, 10)).rstrip("0").rstrip(".")
    if isinstance(v, Date):
        return v.dt().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if isinstance(v, list):
        return ",".join(to_string(x) for x in v)
    return str(v)


def truthy(v) -> bool:
    if isinstance(v, float) and math.isnan(v):
        return False
    return bool(v) if not isinstance(v, Date) else True


def _props(value, path, name, ctx):
    for p in path:
        if p == "displayValue" and not isinstance(value, dict):
            value = ctx.display.get(name, to_string(value))
        elif isinstance(value, dict):
            value = value.get(p, "")
        else:
            value = ""
    return value


def resolve(s: str, ctx: Context):
    m = re.fullmatch(r"\[\$([A-Za-z_]\w*)((?:\.\w+)*)\]", s)
    if m:
        name = m.group(1)
        if name not in ctx.row:
            raise FieldNotInView(name)
        return _props(ctx.row[name], [p for p in m.group(2).split(".") if p], name, ctx)
    m = re.fullmatch(r"@currentField((?:\.\w+)*)", s)
    if m:
        name = ctx.current_field
        if name is None or name not in ctx.row:
            raise FieldNotInView(name or "@currentField")
        return _props(ctx.row[name], [p for p in m.group(1).split(".") if p], name, ctx)
    if s == "@me":
        return ctx.me
    if s == "@now":
        return ctx.now
    if s == "@rowIndex":
        return ctx.row_index
    if s.startswith("@") and re.fullmatch(r"@[A-Za-z_][\w.]*", s):
        raise NotSupportedLocally(f"special value {s}")
    return s


def _compare(op, a, b):
    """Close enough to JavaScript for our formats: two strings compare as text; '==' between text-like values
    compares text; everything else (numbers, dates, booleans, empty) compares as numbers."""
    numeric = (int, float, bool, Date)
    if isinstance(a, str) and isinstance(b, str):
        x, y = a, b
    elif op in ("==", "!=") and not isinstance(a, numeric) and not isinstance(b, numeric):
        x, y = to_string(a), to_string(b)
    else:
        x, y = _num(a), _num(b)
    return {"==": x == y, "!=": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]


def evaluate(ast, ctx: Context):
    if isinstance(ast, str):
        return resolve(ast, ctx)
    if not isinstance(ast, dict):
        return ast
    op = ast["operator"]
    ops = ast.get("operands", [])
    if op == "?":
        return evaluate(ops[1], ctx) if truthy(evaluate(ops[0], ctx)) else evaluate(ops[2], ctx)
    if op == "&&":
        return truthy(evaluate(ops[0], ctx)) and truthy(evaluate(ops[1], ctx))
    if op == "||":
        return truthy(evaluate(ops[0], ctx)) or truthy(evaluate(ops[1], ctx))
    a = [evaluate(o, ctx) for o in ops]
    if op == "+":
        x, y = a
        if isinstance(x, str) or isinstance(y, str):
            return to_string(x) + to_string(y)
        if isinstance(x, Date) and not isinstance(y, Date):
            return Date(int(x.ms + _num(y)))
        return _num(x) + _num(y)
    if op == "-":
        if len(a) == 1:
            return -_num(a[0])
        x, y = a
        if isinstance(x, Date) and not isinstance(y, Date):
            return Date(int(x.ms - _num(y)))
        return _num(x) - _num(y)
    if op in ("*", "/", "%"):
        x, y = _num(a[0]), _num(a[1])
        if op == "*":
            return x * y
        if y == 0:
            return math.nan if x == 0 or op == "%" else math.copysign(math.inf, x)
        return x / y if op == "/" else math.fmod(x, y)
    if op in ("==", "!=", "<", ">", "<=", ">="):
        return _compare(op, a[0], a[1])
    if op == "Number()":
        return _num(a[0])
    if op == "toString()":
        return to_string(a[0])
    if op == "Date()":
        return a[0] if isinstance(a[0], Date) else (Date(int(a[0])) if isinstance(a[0], (int, float)) else Date.parse(str(a[0])))
    if op == "addDays":
        return Date(int(evaluate({"operator": "Date()", "operands": [a[0]]}, ctx).ms + _num(a[1]) * DAY_MS))
    if op == "addMinutes":
        return Date(int(evaluate({"operator": "Date()", "operands": [a[0]]}, ctx).ms + _num(a[1]) * 60_000))
    if op == "toLocaleDateString()":
        if a[0] in ("", None):
            return ""
        d = (a[0] if isinstance(a[0], Date) else Date.parse(str(a[0]))).dt()
        return f"{d.month}/{d.day}/{d.year}"
    if op == "length":
        v = a[0]
        return len(v) if isinstance(v, list) else (1 if truthy(v) else 0)
    if op == "join":
        return a[1].join(to_string(x) for x in a[0]) if isinstance(a[0], list) else to_string(a[0])
    if op == "indexOf":
        return a[0].index(a[1]) if a[1] in a[0] else -1
    if op == "lastIndexOf":
        return a[0].rindex(a[1]) if a[1] in a[0] else -1
    if op == "startsWith":
        return to_string(a[0]).startswith(to_string(a[1]))
    if op == "endsWith":
        return to_string(a[0]).endswith(to_string(a[1]))
    if op == "toLowerCase":
        return to_string(a[0]).lower()
    if op == "toUpperCase":
        return to_string(a[0]).upper()
    if op == "abs":
        return abs(_num(a[0]))
    if op == "floor":
        return math.floor(_num(a[0]))
    if op == "ceiling":
        return math.ceil(_num(a[0]))
    if op == "pow":
        return _num(a[0]) ** _num(a[1])
    if op == "substring":
        s, i, j = to_string(a[0]), int(_num(a[1])), int(_num(a[2]))
        return s[min(i, j):max(i, j)]
    if op == "getDate":
        return a[0].dt().day
    if op == "getMonth":
        return a[0].dt().month - 1
    if op == "getYear":
        return a[0].dt().year
    raise NotSupportedLocally(f"operator {op!r}")
