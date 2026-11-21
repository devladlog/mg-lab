"""A small evaluator for the expression language used by Power Automate cloud flows.

Cloud flows run on the same engine as Azure Logic Apps, and their expressions use the
Workflow Definition Language (WDL). This module implements the subset of WDL that our flows
use, so trigger conditions, conditions and inputs can be unit-tested on a laptop.

It is deliberately strict:
  * ``x['p']`` on a missing property or on null raises, ``x?['p']`` returns null
    (the documented "null ignore" operator).
  * every function argument is evaluated, including both branches of ``if()``.
  * comparison functions refuse null and mixed types instead of guessing.
If something passes here but the real engine is more lenient, nothing breaks. The opposite
(passing here, failing in the cloud) is what we try hard to avoid.

Reference: https://learn.microsoft.com/azure/logic-apps/expression-functions-reference
"""
from __future__ import annotations

import base64
import json
import math
import re
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


class ExpressionError(Exception):
    """Raised for parse errors and for runtime errors the engine would also raise."""


# --------------------------------------------------------------------------- tokens
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>'(?:[^']|'')*')
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[()\[\],?.\-])
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str
    value: Any
    pos: int


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            if text[pos] == "'":
                raise ExpressionError(f"Unterminated string literal at position {pos}: {text!r}")
            raise ExpressionError(f"Unexpected character {text[pos]!r} at position {pos}: {text!r}")
        kind = m.lastgroup
        raw = m.group(kind)
        if kind == "string":
            tokens.append(Token("string", raw[1:-1].replace("''", "'"), pos))
        elif kind == "number":
            tokens.append(Token("number", float(raw) if "." in raw else int(raw), pos))
        elif kind == "ident":
            tokens.append(Token("ident", raw, pos))
        elif kind == "op":
            tokens.append(Token(raw, raw, pos))
        pos = m.end()
    tokens.append(Token("eof", None, pos))
    return tokens


# --------------------------------------------------------------------------- AST
@dataclass
class Lit:
    value: Any


@dataclass
class Call:
    name: str
    args: list


@dataclass
class Index:
    base: Any
    key: Any
    safe: bool


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0

    def peek(self, offset: int = 0) -> Token:
        return self.tokens[self.i + offset]

    def take(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise ExpressionError(
                f"Expected {kind!r} but found {tok.kind!r} at position {tok.pos}: {self.text!r}"
            )
        self.i += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.peek().kind != "eof":
            tok = self.peek()
            raise ExpressionError(f"Unexpected {tok.value!r} at position {tok.pos}: {self.text!r}")
        return node

    def expr(self):
        node = self.primary()
        while True:
            tok = self.peek()
            if tok.kind == "?" and self.peek(1).kind in ("[", "."):
                self.i += 1
                node = self.postfix(node, safe=True)
            elif tok.kind in ("[", "."):
                node = self.postfix(node, safe=False)
            else:
                return node

    def postfix(self, base, safe: bool):
        tok = self.peek()
        if tok.kind == "[":
            self.i += 1
            key = self.expr()
            self.take("]")
            return Index(base, key, safe)
        self.take(".")
        name = self.take("ident").value
        return Index(base, Lit(name), safe)

    def primary(self):
        tok = self.peek()
        if tok.kind == "string":
            self.i += 1
            return Lit(tok.value)
        if tok.kind == "number":
            self.i += 1
            return Lit(tok.value)
        if tok.kind == "-" and self.peek(1).kind == "number":
            self.i += 2
            return Lit(-self.tokens[self.i - 1].value)
        if tok.kind == "ident":
            self.i += 1
            if self.peek().kind == "(":
                self.i += 1
                args = []
                if self.peek().kind != ")":
                    args.append(self.expr())
                    while self.peek().kind == ",":
                        self.i += 1
                        args.append(self.expr())
                self.take(")")
                return Call(tok.value, args)
            low = tok.value.lower()
            if low == "true":
                return Lit(True)
            if low == "false":
                return Lit(False)
            if low == "null":
                return Lit(None)
            raise ExpressionError(
                f"Unknown identifier {tok.value!r} at position {tok.pos} (did you forget the parentheses?): {self.text!r}"
            )
        raise ExpressionError(f"Unexpected {tok.value!r} at position {tok.pos}: {self.text!r}")


def parse(text: str):
    """Parse an expression *without* the leading '@'."""
    return _Parser(text).parse()


def walk(node):
    """Yield every node of an AST (used by the linter)."""
    yield node
    if isinstance(node, Call):
        for a in node.args:
            yield from walk(a)
    elif isinstance(node, Index):
        yield from walk(node.base)
        yield from walk(node.key)


# --------------------------------------------------------------------------- templates
def find_interpolations(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, inner) for each @{...} block, respecting quoted strings."""
    out = []
    i = 0
    while True:
        start = text.find("@{", i)
        if start < 0:
            return out
        if start > 0 and text[start - 1] == "@":  # '@@{' is an escaped literal
            i = start + 2
            continue
        depth, j, in_str = 1, start + 2, False
        while j < len(text) and depth:
            c = text[j]
            if in_str:
                if c == "'":
                    if j + 1 < len(text) and text[j + 1] == "'":
                        j += 1
                    else:
                        in_str = False
            elif c == "'":
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        if depth:
            raise ExpressionError(f"Unterminated @{{ in {text!r}")
        out.append((start, j, text[start + 2 : j - 1]))
        i = j


def expressions_in(value) -> list[str]:
    """Every expression (without '@') found in a JSON value: '@expr' strings and '@{...}' blocks."""
    found: list[str] = []
    if isinstance(value, str):
        if value.startswith("@") and not value.startswith("@@") and not value.startswith("@{"):
            found.append(value[1:])
        else:
            found.extend(inner for _, _, inner in find_interpolations(value))
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(expressions_in(v))
    elif isinstance(value, list):
        for v in value:
            found.extend(expressions_in(v))
    return found


def to_text(value) -> str:
    """How a value is rendered inside an @{...} string interpolation."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    return str(value)


# --------------------------------------------------------------------------- timestamps
from . import timefmt as tf  # noqa: E402
from . import xmlfns  # noqa: E402
from .timefmt import format_timestamp, parse_timestamp  # noqa: E402,F401  (used by episodes 1-2 code)


# --------------------------------------------------------------------------- evaluation
class Context:
    """What an expression can see while a flow runs. The simulator fills these in."""

    def __init__(
        self,
        trigger_outputs: Any = None,
        actions: dict | None = None,
        variables: dict | None = None,
        parameters: dict | None = None,
        now: datetime | None = None,
        workflow: dict | None = None,
    ):
        self.trigger_outputs = trigger_outputs
        self.actions = actions if actions is not None else {}  # name -> {"status","outputs"}
        self.variables = variables if variables is not None else {}
        self.parameters = parameters or {}
        self.now = now or datetime.now(timezone.utc)
        self.workflow = workflow or {}
        self.item_stack: list[Any] = []  # current item() for Query / Table / Select
        self.loop_items: dict[str, Any] = {}  # items('Loop_name')


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _equals(a, b) -> bool:
    # The reference documents equals(true, 1) as true, so booleans compare as 0/1 with numbers.
    if isinstance(a, (bool, int, float)) and isinstance(b, (bool, int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    return a == b


def _compare(name: str, a, b) -> int:
    if _is_num(a) and _is_num(b):
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    raise ExpressionError(
        f"The template language function '{name}' expects two numbers or two strings, got "
        f"{type(a).__name__} and {type(b).__name__} ({a!r}, {b!r})"
    )


def _bool(name: str, v) -> bool:
    if not isinstance(v, bool):
        raise ExpressionError(f"The template language function '{name}' expects booleans, got {v!r}")
    return v


def _need(name: str, args: list, lo: int, hi: int | None = None):
    hi = lo if hi is None else hi
    if not (lo <= len(args) <= hi):
        expected = str(lo) if lo == hi else f"{lo}-{hi}"
        raise ExpressionError(f"The template language function '{name}' expects {expected} arguments, got {len(args)}")


def _action_record(ctx: Context, name: str) -> dict:
    if name not in ctx.actions:
        raise ExpressionError(f"The action '{name}' hasn't run (unknown action or not executed yet)")
    rec = ctx.actions[name]
    if rec["status"] == "Skipped":
        raise ExpressionError(f"The action '{name}' was skipped, so its outputs can't be referenced")
    return rec


def _length(v):
    if isinstance(v, (str, list, dict)):
        return len(v)
    raise ExpressionError(f"length() expects a string or an array, got {v!r}")


def _empty(v):
    if v is None:
        return True
    if isinstance(v, (str, list, dict)):
        return len(v) == 0
    raise ExpressionError(f"empty() expects a string, array or object, got {v!r}")


def _contains(coll, value):
    if isinstance(coll, str):
        if not isinstance(value, str):
            raise ExpressionError("contains() on a string expects a string to search for")
        return value in coll
    if isinstance(coll, list):
        return any(_equals(x, value) for x in coll)
    if isinstance(coll, dict):
        return value in coll
    raise ExpressionError(f"contains() expects a string, array or object, got {coll!r}")


def _to_int(v):
    if isinstance(v, bool):
        raise ExpressionError(f"int() can't convert {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*-?\d+\s*", v):
        return int(v)
    raise ExpressionError(f"int() can't convert {v!r}")


def _to_float(v):
    if _is_num(v):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            pass
    raise ExpressionError(f"float() can't convert {v!r}")


def _arith(name, a, b, op):
    if not (_is_num(a) and _is_num(b)):
        raise ExpressionError(f"{name}() expects two numbers, got {a!r} and {b!r}")
    return op(a, b)


def _div(a, b):
    if b == 0:
        raise ExpressionError("div() by zero")
    if isinstance(a, int) and isinstance(b, int):
        return int(a / b)  # integer division truncates toward zero
    return a / b


def _add_time(ts, amount, unit, fmt="o"):
    if not _is_num(amount):
        raise ExpressionError(f"Expected a number of {unit}, got {amount!r}")
    st = _stamp(ts)
    return tf.format_stamp(tf.Stamp(st.wall + timedelta(**{unit: amount}), st.kind), fmt)


def _stamp(ts) -> "tf.Stamp":
    try:
        return tf.parse_stamp(ts)
    except tf.TimeError as e:
        raise ExpressionError(str(e)) from None


def _tf(fn):
    """Run a timefmt/xml helper and turn its errors into template errors, like the engine."""
    def wrapper(*args):
        try:
            return fn(*args)
        except (tf.TimeError, xmlfns.XmlError) as e:
            raise ExpressionError(str(e)) from None
    return wrapper


_UNITS = {"second": "seconds", "minute": "minutes", "hour": "hours", "day": "days", "week": "weeks"}


def _add_to_time(ts, interval, unit, fmt="o", sign=1):
    key = str(unit).lower().rstrip("s")
    if key == "month" or key == "year":
        st = _stamp(ts)
        months = interval * (12 if key == "year" else 1) * sign
        y, m = divmod(st.wall.month - 1 + months, 12)
        wall = st.wall.replace(year=st.wall.year + y, month=m + 1)
        return tf.format_stamp(tf.Stamp(wall, st.kind), fmt)
    if key not in _UNITS:
        raise ExpressionError(f"Unknown time unit {unit!r}")
    return _add_time(ts, interval * sign, _UNITS[key], fmt)


def _start_of(ts, part, fmt="o"):
    st = _stamp(ts)
    w = st.wall
    if part == "day":
        w = w.replace(hour=0, minute=0, second=0, microsecond=0)
    elif part == "hour":
        w = w.replace(minute=0, second=0, microsecond=0)
    else:
        w = w.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return tf.format_stamp(tf.Stamp(w, st.kind), fmt)


def _convert_from_utc(ts, tz, fmt="o"):
    return tf.format_stamp(tf.from_utc(_stamp(ts), tz), fmt)


def _convert_to_utc(ts, tz, fmt="o"):
    return tf.format_stamp(tf.to_utc(_stamp(ts), tz), fmt)


def _convert_time_zone(ts, src, dst, fmt="o"):
    st = _stamp(ts)
    utc = st if (st.kind == tf.UTC_KIND) else tf.to_utc(st, src)
    return tf.format_stamp(tf.from_utc(utc, dst), fmt)


def _day_of_week(ts):
    return (_stamp(ts).wall.weekday() + 1) % 7  # Sunday is 0, Monday is 1


def _date_difference(start, end):
    return tf.timespan(_stamp(end).wall - _stamp(start).wall)


def _ticks(dt) -> int:
    return tf.ticks(_stamp(dt) if isinstance(dt, str) else tf.Stamp(dt.replace(tzinfo=None), tf.UTC_KIND))


# --- strings
def _index_of(text, search):
    _strings("indexOf", text, search)
    return text.lower().find(search.lower())  # documented: not case-sensitive


def _last_index_of(text, search):
    _strings("lastIndexOf", text, search)
    if search == "":  # documented edge cases
        return 0 if text == "" else len(text) - 1
    return text.lower().rfind(search.lower())


def _strings(name, *args):
    for a in args:
        if not isinstance(a, str):
            raise ExpressionError(f"{name}() expects strings, got {a!r}")


def _substring(text, start, length=None):
    _strings("substring", text)
    if start < 0 or start > len(text) or (length is not None and (length < 0 or start + length > len(text))):
        raise ExpressionError(f"substring({text!r}, {start}, {length}): the index and length must refer to a "
                              f"location within the string")
    return text[start:] if length is None else text[start:start + length]


def _slice(text, start, end=None):
    _strings("slice", text)
    n = len(text)
    s = start + n if start < 0 else start
    e = n if end is None else (end + n if end < 0 else end)
    s, e = max(0, min(s, n)), max(0, min(e, n))
    return text[s:e] if s < e else ""


def _split(text, sep):
    _strings("split", text, sep)
    return text.split(sep)


def _is_int(text):
    _strings("isInt", text)
    return bool(re.fullmatch(r"\s*[-+]?\d+\s*", text))


def _is_float(text, locale=None):
    _strings("isFloat", text)
    if locale and locale.lower() not in ("en-us",):
        if locale.lower() == "de-de":
            text = text.replace(".", "").replace(",", ".")
        else:
            raise ExpressionError(f"flowkit's isFloat() doesn't know locale {locale!r}")
    else:
        text = text.replace(",", "")
    try:
        float(text)
        return True
    except ValueError:
        return False


# --- collections
def _need_array(name, v):
    if not isinstance(v, list):
        raise ExpressionError(f"{name}() expects an array, got {v!r}")
    return v


def _take(coll, n):
    if isinstance(coll, (str, list)):
        return coll[: max(0, n)]
    raise ExpressionError(f"take() expects a string or an array, got {coll!r}")


def _skip(coll, n):
    if isinstance(coll, (str, list)):
        return coll[max(0, n):]
    raise ExpressionError(f"skip() expects a string or an array, got {coll!r}")


def _sort(coll, key=None):
    _need_array("sort", coll)
    if key is None:
        values = coll
    else:
        values = []
        for item in coll:
            if not isinstance(item, dict) or key not in item:
                raise ExpressionError(f"sort(): item {item!r} has no key {key!r}")
            values.append(item[key])
    kinds = {("number" if _is_num(v) else type(v).__name__) for v in values}
    if len(kinds) > 1:
        raise ExpressionError(f"sort(): can't compare mixed types {sorted(kinds)}")
    if kinds and kinds.pop() not in ("number", "str", "bool"):
        raise ExpressionError("sort(): the sort key must be a primitive (int, float, string or bool)")
    order = sorted(range(len(coll)), key=lambda i: values[i])  # stable
    return [coll[i] for i in order]


def _union(*colls):
    if all(isinstance(c, dict) for c in colls):
        out = {}
        for c in colls:
            out.update(c)  # "the last item with that name appears in the result"
        return out
    out = []
    for c in colls:
        for item in _need_array("union", c):
            if not any(_same(item, x) for x in out):
                out.append(item)
    return out


def _intersection(*colls):
    if all(isinstance(c, dict) for c in colls):
        keys = [k for k in colls[0] if all(k in c and c[k] == colls[0][k] for c in colls[1:])]
        return {k: colls[-1][k] for k in keys}
    first, *rest = [_need_array("intersection", c) for c in colls]
    out = []
    for item in first:
        if all(any(_same(item, x) for x in r) for r in rest) and not any(_same(item, x) for x in out):
            out.append(item)
    return out


def _same(a, b) -> bool:
    return type(a) is type(b) and a == b if not (_is_num(a) and _is_num(b)) else a == b


def _chunk(coll, size):
    if not isinstance(coll, (str, list)) or not isinstance(size, int) or size < 1:
        raise ExpressionError(f"chunk() expects a string or an array and a positive length, got {coll!r}, {size!r}")
    return [coll[i:i + size] for i in range(0, len(coll), size)]


def _range(start, count):
    if not isinstance(start, int) or not isinstance(count, int) or count < 0:
        raise ExpressionError("range() expects an integer start and a non-negative count")
    return list(range(start, start + count))


def _min_max(name, fn, *args):
    values = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
    if not values or not all(_is_num(v) for v in values):
        raise ExpressionError(f"{name}() expects numbers, got {values!r}")
    return fn(values)


def _json(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise ExpressionError(f"json() expects a string, got {value!r}")
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise ExpressionError(f"json(): {e}") from None


def _add_property(obj, prop, value):
    if not isinstance(obj, dict):
        raise ExpressionError("addProperty() expects an object")
    if prop in obj:
        raise ExpressionError(f"addProperty(): the property {prop!r} already exists (use setProperty)")
    return {**obj, prop: value}


def _set_property(obj, prop, value):
    if not isinstance(obj, dict):
        raise ExpressionError("setProperty() expects an object")
    return {**obj, prop: value}


def _remove_property(obj, prop):
    if not isinstance(obj, dict):
        raise ExpressionError("removeProperty() expects an object")
    return {k: v for k, v in obj.items() if k != prop}


def _mod(a, b):
    if not (_is_num(a) and _is_num(b)):
        raise ExpressionError(f"mod() expects two numbers, got {a!r} and {b!r}")
    if b == 0:
        raise ExpressionError("mod() by zero")
    return int(math.fmod(a, b)) if isinstance(a, int) and isinstance(b, int) else math.fmod(a, b)


def _first(v):
    if isinstance(v, (str, list)):
        return v[0] if v else None
    raise ExpressionError(f"first() expects a string or an array, got {v!r}")


def _last(v):
    if isinstance(v, (str, list)):
        return v[-1] if v else None
    raise ExpressionError(f"last() expects a string or an array, got {v!r}")


def _str_fn(name, fn):
    def wrapper(*args):
        for a in args:
            if not isinstance(a, str):
                raise ExpressionError(f"{name}() expects strings, got {a!r}")
        return fn(*args)

    return wrapper


def _str_arg(name, v):
    if not isinstance(v, str):
        raise ExpressionError(f"{name}() expects a string, got {v!r}")
    return v


def _concat(*args):
    return "".join(to_text(a) for a in args)


def _builtin(ctx: Context) -> dict[str, tuple[int, int, Callable]]:
    return {
        # logical / comparison
        "equals": (2, 2, _equals),
        "and": (1, 99, lambda *a: all(_bool("and", x) for x in a)),
        "or": (1, 99, lambda *a: any(_bool("or", x) for x in a)),
        "not": (1, 1, lambda a: not _bool("not", a)),
        "if": (3, 3, lambda c, t, f: t if _bool("if", c) else f),
        "greater": (2, 2, lambda a, b: _compare("greater", a, b) > 0),
        "greaterorequals": (2, 2, lambda a, b: _compare("greaterOrEquals", a, b) >= 0),
        "less": (2, 2, lambda a, b: _compare("less", a, b) < 0),
        "lessorequals": (2, 2, lambda a, b: _compare("lessOrEquals", a, b) <= 0),
        "coalesce": (1, 99, lambda *a: next((x for x in a if x is not None), None)),
        "empty": (1, 1, _empty),
        "contains": (2, 2, _contains),
        # strings
        "concat": (1, 99, _concat),
        "tolower": (1, 1, _str_fn("toLower", str.lower)),
        "toupper": (1, 1, _str_fn("toUpper", str.upper)),
        "trim": (1, 1, _str_fn("trim", str.strip)),
        "startswith": (2, 2, _str_fn("startsWith", lambda s, p: s.lower().startswith(p.lower()))),
        "endswith": (2, 2, _str_fn("endsWith", lambda s, p: s.lower().endswith(p.lower()))),
        "replace": (3, 3, _str_fn("replace", lambda s, o, n: s.replace(o, n))),
        "string": (1, 1, to_text),
        "length": (1, 1, _length),
        # collections
        "first": (1, 1, _first),
        "last": (1, 1, _last),
        "createarray": (0, 99, lambda *a: list(a)),
        "join": (2, 2, lambda arr, sep: sep.join(to_text(x) for x in arr)),
        # numbers
        "int": (1, 1, _to_int),
        "float": (1, 1, _to_float),
        "add": (2, 2, lambda a, b: _arith("add", a, b, lambda x, y: x + y)),
        "sub": (2, 2, lambda a, b: _arith("sub", a, b, lambda x, y: x - y)),
        "mul": (2, 2, lambda a, b: _arith("mul", a, b, lambda x, y: x * y)),
        "div": (2, 2, lambda a, b: _arith("div", a, b, _div)),
        # dates and time zones (Windows time zone ids)
        "utcnow": (0, 1, lambda fmt="o": tf.format_stamp(tf.Stamp(ctx.now.astimezone(timezone.utc).replace(tzinfo=None), tf.UTC_KIND), fmt)),
        "addseconds": (2, 3, lambda ts, n, fmt="o": _add_time(ts, n, "seconds", fmt)),
        "addminutes": (2, 3, lambda ts, n, fmt="o": _add_time(ts, n, "minutes", fmt)),
        "addhours": (2, 3, lambda ts, n, fmt="o": _add_time(ts, n, "hours", fmt)),
        "adddays": (2, 3, lambda ts, n, fmt="o": _add_time(ts, n, "days", fmt)),
        "addtotime": (3, 4, lambda ts, n, unit, fmt="o": _add_to_time(ts, n, unit, fmt)),
        "subtractfromtime": (3, 4, lambda ts, n, unit, fmt="o": _add_to_time(ts, n, unit, fmt, sign=-1)),
        "startofday": (1, 2, _tf(lambda ts, fmt="o": _start_of(ts, "day", fmt))),
        "startofhour": (1, 2, _tf(lambda ts, fmt="o": _start_of(ts, "hour", fmt))),
        "startofmonth": (1, 2, _tf(lambda ts, fmt="o": _start_of(ts, "month", fmt))),
        "dayofweek": (1, 1, _day_of_week),
        "dayofmonth": (1, 1, lambda ts: _stamp(ts).wall.day),
        "dayofyear": (1, 1, lambda ts: _stamp(ts).wall.timetuple().tm_yday),
        "datedifference": (2, 2, _date_difference),
        "ticks": (1, 1, _ticks),
        "formatdatetime": (1, 3, _tf(lambda ts, fmt="o", locale=None: tf.format_stamp(_stamp(ts), fmt, locale))),
        "convertfromutc": (2, 3, _tf(_convert_from_utc)),
        "converttoutc": (2, 3, _tf(_convert_to_utc)),
        "converttimezone": (3, 4, _tf(_convert_time_zone)),
        # more strings
        "indexof": (2, 2, _index_of),
        "lastindexof": (2, 2, _last_index_of),
        "substring": (2, 3, _substring),
        "slice": (2, 3, _slice),
        "split": (2, 2, _split),
        "isint": (1, 1, _is_int),
        "isfloat": (1, 2, _is_float),
        "formatnumber": (2, 3, _tf(tf.format_number)),
        "uricomponent": (1, 1, lambda s: urllib.parse.quote(_str_arg("uriComponent", s), safe="")),
        "base64": (1, 1, lambda s: base64.b64encode(to_text(s).encode()).decode()),
        "base64tostring": (1, 1, lambda s: base64.b64decode(_str_arg("base64ToString", s)).decode()),
        "guid": (0, 1, lambda fmt="D": str(uuid.uuid4())),
        # more collections and objects
        "take": (2, 2, _take),
        "skip": (2, 2, _skip),
        "sort": (1, 2, _sort),
        "reverse": (1, 1, lambda c: list(reversed(_need_array("reverse", c)))),
        "union": (2, 99, _union),
        "intersection": (2, 99, _intersection),
        "chunk": (2, 2, _chunk),
        "range": (2, 2, _range),
        "min": (1, 99, lambda *a: _min_max("min", min, *a)),
        "max": (1, 99, lambda *a: _min_max("max", max, *a)),
        "mod": (2, 2, _mod),
        "json": (1, 1, _json),
        "addproperty": (3, 3, _add_property),
        "setproperty": (3, 3, _set_property),
        "removeproperty": (2, 2, _remove_property),
        "xml": (1, 1, _tf(xmlfns.to_xml)),
        "xpath": (2, 2, _tf(xmlfns.xpath)),
        # workflow
        "trigger": (0, 0, lambda: ctx.trigger_outputs),
        "triggeroutputs": (0, 0, lambda: ctx.trigger_outputs),
        "triggerbody": (0, 0, lambda: (ctx.trigger_outputs or {}).get("body") if isinstance(ctx.trigger_outputs, dict) else None),
        "outputs": (1, 1, lambda n: _action_record(ctx, n)["outputs"]),
        "body": (1, 1, lambda n: _body_of(_action_record(ctx, n))),
        "actions": (1, 1, lambda n: _action_record(ctx, n)),
        "variables": (1, 1, lambda n: _variable(ctx, n)),
        "parameters": (1, 1, lambda n: _parameter(ctx, n)),
        "item": (0, 0, lambda: _current_item(ctx)),
        "items": (1, 1, lambda n: _loop_item(ctx, n)),
        "workflow": (0, 0, lambda: ctx.workflow),
    }


def _body_of(rec: dict):
    out = rec["outputs"]
    if isinstance(out, dict) and "body" in out:
        return out["body"]
    return out


def _variable(ctx: Context, name: str):
    if name not in ctx.variables:
        raise ExpressionError(f"The variable '{name}' isn't initialized")
    return ctx.variables[name]


def _parameter(ctx: Context, name: str):
    if name not in ctx.parameters:
        raise ExpressionError(f"The workflow parameter '{name}' isn't defined")
    return ctx.parameters[name]


def _current_item(ctx: Context):
    if not ctx.item_stack:
        raise ExpressionError("item() can only be used inside a loop, Filter array, Select or Create table")
    return ctx.item_stack[-1]


def _loop_item(ctx: Context, name: str):
    if name not in ctx.loop_items:
        raise ExpressionError(f"items('{name}') is only valid inside the loop '{name}'")
    return ctx.loop_items[name]


def _index(base, key, safe: bool):
    if base is None:
        if safe:
            return None
        raise ExpressionError(f"Can't select property {key!r} of null (use ?[{key!r}] if it may be missing)")
    if isinstance(base, dict):
        if not isinstance(key, str):
            raise ExpressionError(f"Object properties are selected with strings, got {key!r}")
        if key in base:
            return base[key]
        if "/" in key:  # designer shorthand: outputs('X')?['body/outcome']
            cur = base
            for part in key.split("/"):
                cur = _index(cur, part, safe)
            return cur
        if safe:
            return None
        raise ExpressionError(f"Property {key!r} doesn't exist; available: {sorted(base)[:10]}")
    if isinstance(base, list):
        if not _is_num(key) or not float(key).is_integer():
            raise ExpressionError(f"Array elements are selected with integers, got {key!r}")
        k = int(key)
        if 0 <= k < len(base):
            return base[k]
        if safe:
            return None
        raise ExpressionError(f"Index {k} is out of range for an array of {len(base)}")
    if safe:
        return None
    raise ExpressionError(f"Can't select {key!r} from a {type(base).__name__}")


def known_functions() -> set[str]:
    """Lower-case names of every function this evaluator implements (used by the linter)."""
    return set(_builtin(Context()).keys())


def evaluate_ast(node, ctx: Context):
    if isinstance(node, Lit):
        return node.value
    if isinstance(node, Index):
        return _index(evaluate_ast(node.base, ctx), evaluate_ast(node.key, ctx), node.safe)
    if isinstance(node, Call):
        table = _builtin(ctx)
        key = node.name.lower()
        if key not in table:
            raise ExpressionError(f"The template function '{node.name}' isn't supported by this evaluator")
        lo, hi, fn = table[key]
        args = [evaluate_ast(a, ctx) for a in node.args]  # eager, like the engine
        _need(node.name, args, lo, hi)
        return fn(*args)
    raise ExpressionError(f"Unknown node {node!r}")


def evaluate(expression: str, ctx: Context):
    """Evaluate one expression. Accepts it with or without the leading '@'."""
    text = expression[1:] if expression.startswith("@") else expression
    return evaluate_ast(parse(text), ctx)


def evaluate_value(value, ctx: Context):
    """Evaluate a JSON value from a flow definition: '@expr', '@{...}' interpolation, nested objects."""
    if isinstance(value, str):
        if value.startswith("@@"):
            return value[1:]
        if value.startswith("@") and not value.startswith("@{"):
            return evaluate(value[1:], ctx)
        blocks = find_interpolations(value)
        if not blocks:
            return value.replace("@@", "@")
        if len(blocks) == 1 and blocks[0][0] == 0 and blocks[0][1] == len(value):
            return to_text(evaluate(blocks[0][2], ctx))
        out, last = [], 0
        for start, end, inner in blocks:
            out.append(value[last:start])
            out.append(to_text(evaluate(inner, ctx)))
            last = end
        out.append(value[last:])
        return "".join(out)
    if isinstance(value, dict):
        return {k: evaluate_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [evaluate_value(v, ctx) for v in value]
    return value


def evaluate_condition(expression, ctx: Context) -> bool:
    """Evaluate an If action's expression: a string ('@equals(...)') or the designer's object form."""
    if isinstance(expression, str):
        result = evaluate_value(expression, ctx)
    elif isinstance(expression, dict):
        result = _object_condition(expression, ctx)
    else:
        raise ExpressionError(f"Unsupported condition {expression!r}")
    if not isinstance(result, bool):
        raise ExpressionError(f"A condition must evaluate to true or false, got {result!r}")
    return result


_OBJECT_OPS = {
    "equals": lambda a, b: _equals(a, b),
    "greater": lambda a, b: _compare("greater", a, b) > 0,
    "greaterOrEquals": lambda a, b: _compare("greaterOrEquals", a, b) >= 0,
    "less": lambda a, b: _compare("less", a, b) < 0,
    "lessOrEquals": lambda a, b: _compare("lessOrEquals", a, b) <= 0,
    "contains": _contains,
    "startsWith": lambda s, p: _str_fn("startsWith", lambda x, y: x.lower().startswith(y.lower()))(s, p),
    "endsWith": lambda s, p: _str_fn("endsWith", lambda x, y: x.lower().endswith(y.lower()))(s, p),
}


def _object_condition(node: dict, ctx: Context) -> bool:
    if len(node) != 1:
        raise ExpressionError(f"Condition objects have exactly one operator, got {list(node)}")
    op, operand = next(iter(node.items()))
    if op == "and":
        return all([_object_condition(n, ctx) for n in operand])
    if op == "or":
        return any([_object_condition(n, ctx) for n in operand])
    if op == "not":
        return not _object_condition(operand, ctx)
    if op in _OBJECT_OPS:
        a, b = (evaluate_value(x, ctx) for x in operand)
        return _OBJECT_OPS[op](a, b)
    raise ExpressionError(f"Unknown condition operator {op!r}")
