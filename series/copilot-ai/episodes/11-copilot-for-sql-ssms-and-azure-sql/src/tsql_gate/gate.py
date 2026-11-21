"""The review gate: split a T-SQL script into batches, then report what it would do.

Two layers, on purpose:
1. A keyword scan over the script with comments, strings and quoted identifiers blanked out. It is conservative: if a
   write keyword is anywhere in the script, the script is a write script. This layer needs no parser and cannot be
   fooled by a statement sqlglot does not understand.
2. sqlglot (T-SQL dialect) for the structural rules: UPDATE/DELETE without WHERE, SELECT *, unqualified table names.
   If sqlglot cannot parse a batch the gate fails closed (TG-P001, BLOCK).

Modes:
  readonly  (default) only reads are allowed; any write, DDL, permission change or unknown EXEC is a BLOCK.
  readwrite           writes are allowed but reviewed (see the rule table in README.md).
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

logging.getLogger("sqlglot").setLevel(logging.ERROR)  # "contains unsupported syntax" noise: we handle Command nodes


class Severity(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass
class Finding:
    rule: str
    severity: Severity
    line: int
    message: str
    snippet: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


RULES = {
    "TG-P001": "Batch could not be parsed: the gate cannot prove it is safe (fails closed)",
    "TG-W001": "Write, DDL or permission statement in read-only mode",
    "TG-W002": "UPDATE or DELETE without a WHERE clause",
    "TG-W003": "TRUNCATE TABLE, or DROP without IF EXISTS (the constitution rules in CONSTITUTION.md)",
    "TG-W004": "SELECT ... INTO creates a table",
    "TG-S001": "Dangerous feature: xp_ procedures, sp_configure, OLE automation, OPENROWSET and friends",
    "TG-S002": "Permission or execution-context change (GRANT, DENY, REVOKE, EXECUTE AS, role membership, logins)",
    "TG-D001": "Dynamic SQL (EXEC of a string or sp_executesql): literal text is analysed, variables cannot be",
    "TG-E001": "EXEC of a procedure the gate cannot show is read-only",
    "TG-Q001": "SELECT * (explicit column lists, as the database constitution asks)",
    "TG-Q002": "Object name without a schema (schema-qualify, as the database constitution asks)",
}

# --- 1. masking ------------------------------------------------------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z_#@][A-Za-z0-9_#@$]*")


def mask(text: str) -> str:
    """Return text of the same length with comments, string literals and quoted identifiers blanked out.

    Newlines are kept, so offsets and line numbers still match the original."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
        elif c == "/" and nxt == "*":
            depth, j = 1, i + 2
            out[i] = out[i + 1] = " "
            while j < n and depth:
                if text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    depth += 1
                    out[j] = out[j + 1] = " "
                    j += 2
                elif text[j] == "*" and j + 1 < n and text[j + 1] == "/":
                    depth -= 1
                    out[j] = out[j + 1] = " "
                    j += 2
                else:
                    if text[j] != "\n":
                        out[j] = " "
                    j += 1
            i = j
        elif c in ("'", '"', "["):
            close = {"'": "'", '"': '"', "[": "]"}[c]
            j = i + 1
            while j < n:
                if text[j] == close:
                    if j + 1 < n and text[j + 1] == close:  # '' and "" and ]] are escapes
                        out[j] = out[j + 1] = "x" if c != "'" else " "
                        j += 2
                        continue
                    break
                if text[j] != "\n":
                    out[j] = "x" if c != "'" else " "
                j += 1
            i = j + 1
        else:
            i += 1
    return "".join(out)


@dataclass
class Batch:
    text: str
    start_line: int  # 1-based line of the first line of the batch in the original file


_GO = re.compile(r"^\s*GO(?:\s+\d+)?\s*(?:--.*)?$", re.IGNORECASE)


def split_batches(text: str) -> list[Batch]:
    """Split on lines that contain only GO (the SSMS/sqlcmd batch separator), outside comments and strings."""
    masked_lines = mask(text).split("\n")
    lines = text.split("\n")
    batches: list[Batch] = []
    cur: list[str] = []
    start = 1
    for idx, (orig, m) in enumerate(zip(lines, masked_lines), start=1):
        # GO is only a separator when it is alone on a line of the masked text (so not inside a block comment/string)
        if _GO.match(m) and orig.strip().upper().startswith("GO"):
            if any(s.strip() for s in cur):
                batches.append(Batch("\n".join(cur), start))
            cur, start = [], idx + 1
        else:
            if not cur:
                start = idx
            cur.append(orig)
    if any(s.strip() for s in cur):
        batches.append(Batch("\n".join(cur), start))
    return batches


# --- 2. rules ----------------------------------------------------------------------------------------------------

WRITE_WORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "CREATE", "ALTER", "DROP",
    "BACKUP", "RESTORE", "SHUTDOWN", "KILL", "RECONFIGURE", "DBCC",
}
PERMISSION_WORDS = {"GRANT", "DENY", "REVOKE"}
DANGEROUS = re.compile(
    r"\b(xp_\w+|sp_configure|sp_OA\w+|OPENROWSET|OPENDATASOURCE|OPENQUERY|sp_addsrvrolemember|sp_addrolemember|"
    r"sp_dropsrvrolemember|sp_droprolemember)\b",
    re.IGNORECASE,
)
# system procedures that only read (sp_help family and a few catalog procedures). Anything else is "unknown".
READONLY_PROCS = {
    "sp_help", "sp_helptext", "sp_helpindex", "sp_helpconstraint", "sp_helpdb", "sp_helpuser", "sp_helprole",
    "sp_helprolemember", "sp_helpsrvrole", "sp_helpsrvrolemember", "sp_helplanguage", "sp_helpfile",
    "sp_helpfilegroup", "sp_spaceused", "sp_who", "sp_who2", "sp_columns", "sp_tables", "sp_databases",
    "sp_stored_procedures", "sp_pkeys", "sp_fkeys", "sp_sproc_columns", "sp_server_info", "sp_describe_first_result_set",
}
_EXEC = re.compile(r"\bEXEC(?:UTE)?\b\s*(?:@\w+\s*=\s*)?(\(|AS\b|[\[\]\w.#@$]+)", re.IGNORECASE)
_EXECSQL_LITERAL = re.compile(r"\bsp_executesql\s+N?'((?:[^']|'')*)'", re.IGNORECASE)
_EXEC_LITERAL = re.compile(r"\bEXEC(?:UTE)?\s*\(\s*N?'((?:[^']|'')*)'\s*\)", re.IGNORECASE)


def _line_of(text: str, offset: int, base: int) -> int:
    return base + text.count("\n", 0, offset)


def _snippet(text: str, offset: int) -> str:
    end = text.find("\n", offset)
    s = text[offset: end if end != -1 else None].strip()
    return s[:90]


def _words(masked: str):
    for m in _TOKEN.finditer(masked):
        yield m.group(0), m.start()


def _keyword_scan(batch: Batch, masked: str, mode: str, depth: int) -> list[Finding]:
    f: list[Finding] = []
    base, text = batch.start_line, batch.text
    read_only = mode == "readonly"
    toks = list(_words(masked))
    upper = [(w.upper(), p) for w, p in toks]
    names = {w for w, _ in upper}

    for k, (w, pos) in enumerate(upper):
        if w in WRITE_WORDS:
            if w == "TRUNCATE":
                f.append(Finding("TG-W003", Severity.BLOCK, _line_of(text, pos, base),
                                 "TRUNCATE TABLE is not allowed by the database constitution", _snippet(text, pos)))
            elif w == "DROP":
                # DROP <object> IF EXISTS <name> : the gate only reports DROP IF EXISTS as acceptable (WARN) in readwrite
                window = [x for x, _ in upper[k + 1: k + 5]]
                if "IF" in window and "EXISTS" in window:
                    sev, msg = Severity.WARN, "DROP ... IF EXISTS removes an object: review the name"
                else:
                    sev, msg = Severity.BLOCK, "DROP without IF EXISTS"
                f.append(Finding("TG-W003", sev, _line_of(text, pos, base), msg, _snippet(text, pos)))
            if read_only:
                f.append(Finding("TG-W001", Severity.BLOCK, _line_of(text, pos, base),
                                 f"{w} is a write/DDL statement and the mode is read-only", _snippet(text, pos)))
        elif w in PERMISSION_WORDS:
            sev = Severity.BLOCK if read_only else Severity.WARN
            f.append(Finding("TG-S002", sev, _line_of(text, pos, base),
                             f"{w} changes permissions", _snippet(text, pos)))
        elif w == "INTO":
            prev = [x for x, _ in upper[max(0, k - 3): k]]
            if "INSERT" not in prev and "MERGE" not in prev and "SELECT" in {x for x, _ in upper[:k]}:
                f.append(Finding("TG-W004", Severity.BLOCK if read_only else Severity.WARN, _line_of(text, pos, base),
                                 "SELECT ... INTO creates a table", _snippet(text, pos)))

    for m in DANGEROUS.finditer(masked):
        f.append(Finding("TG-S001", Severity.BLOCK, _line_of(text, m.start(), base),
                         f"{m.group(0)} is on the dangerous-feature list", _snippet(text, m.start())))

    # permission-related phrases that start with other keywords
    for m in re.finditer(r"\b(?:ADD|DROP)\s+MEMBER\b|\bCREATE\s+(?:LOGIN|USER)\b|\bALTER\s+(?:LOGIN|USER|ROLE|SERVER)\b|"
                         r"\bEXEC(?:UTE)?\s+AS\b", masked, re.IGNORECASE):
        sev = Severity.BLOCK if read_only else Severity.WARN
        phrase = " ".join(m.group(0).split()).upper()
        f.append(Finding("TG-S002", sev, _line_of(text, m.start(), base),
                         f"{phrase} changes principals or execution context", _snippet(text, m.start())))

    # EXEC
    for m in _EXEC.finditer(masked):
        target = m.group(1)
        line = _line_of(text, m.start(), base)
        if target.upper() == "AS":
            continue  # reported as TG-S002 above
        if target == "(":
            lit = _EXEC_LITERAL.search(text, m.start())
            if lit and lit.start() == m.start() and depth < 2:
                f.append(Finding("TG-D001", Severity.WARN, line, "EXEC of a literal string: analysed below",
                                 _snippet(text, m.start())))
                f.extend(_analyse_literal(lit.group(1), batch, line, mode, depth))
            else:
                f.append(Finding("TG-D001", Severity.BLOCK if read_only else Severity.WARN, line,
                                 "EXEC of a variable or expression: the text is not known before it runs",
                                 _snippet(text, m.start())))
            continue
        simple = target.split(".")[-1].strip("[]").lower()
        if simple == "sp_executesql":
            lit = _EXECSQL_LITERAL.search(text, m.start())
            if lit and lit.start() >= m.start() and depth < 2:
                f.append(Finding("TG-D001", Severity.WARN, line, "sp_executesql with a literal: analysed below",
                                 _snippet(text, m.start())))
                f.extend(_analyse_literal(lit.group(1), batch, line, mode, depth))
            else:
                f.append(Finding("TG-D001", Severity.BLOCK if read_only else Severity.WARN, line,
                                 "sp_executesql with a variable: the text is not known before it runs",
                                 _snippet(text, m.start())))
        elif simple in READONLY_PROCS and (target.lower().startswith("sp_") or target.lower().startswith("dbo.sp_")
                                           or target.lower().startswith("sys.sp_")):
            continue
        elif re.match(r"xp_", simple):
            continue  # TG-S001 already
        else:
            f.append(Finding("TG-E001", Severity.BLOCK if read_only else Severity.WARN, line,
                             f"EXEC {target}: the gate cannot show this procedure is read-only", _snippet(text, m.start())))
    return f


def _analyse_literal(sql: str, outer: Batch, line: int, mode: str, depth: int) -> list[Finding]:
    inner = sql.replace("''", "'")
    sub = check_text(inner, mode=mode, _depth=depth + 1)
    return [Finding(x.rule, x.severity, line, f"(inside dynamic SQL) {x.message}", x.snippet) for x in sub
            if x.rule not in {"TG-D001"} or x.severity == Severity.BLOCK]


def _parse(batch_text: str):
    try:
        return sqlglot.parse(batch_text, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)
    except SqlglotError:
        pass
    # second chance: T-SQL allows statements without semicolons; sqlglot does not. Add one before a line that starts
    # a new statement, unless the line continues the previous one (INSERT ... SELECT, UNION SELECT, ...).
    fixed = _add_semicolons(batch_text)
    if fixed != batch_text:
        try:
            return sqlglot.parse(fixed, read="tsql", error_level=sqlglot.ErrorLevel.RAISE)
        except SqlglotError:
            return None
    return None


_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|DROP|TRUNCATE|ALTER|CREATE|EXEC|EXECUTE|DECLARE|SET|USE|"
                    r"WITH|IF|WHILE|PRINT|GRANT|DENY|REVOKE)\b", re.IGNORECASE)
_CONTINUES = re.compile(r"(UNION|ALL|INTERSECT|EXCEPT|AS|AND|OR|ON|IN|EXISTS|BY|FROM|JOIN|THEN|ELSE|BEGIN|SELECT|INSERT|"
                        r"INTO|VALUES|SET|WHERE|HAVING|OVER|APPLY)\s*$|[,(=<>+\-*/]\s*$", re.IGNORECASE)


def _add_semicolons(text: str) -> str:
    masked = mask(text).split("\n")
    lines = text.split("\n")
    out: list[str] = []
    prev_masked = ""
    stmt_is_insert = False
    for orig, m in zip(lines, masked):
        if _START.match(m) and prev_masked.strip() and not prev_masked.rstrip().endswith(";"):
            first = _START.match(m).group(1).upper()
            continues = bool(_CONTINUES.search(prev_masked)) or (stmt_is_insert and first == "SELECT")
            if not continues:
                out[-1] = out[-1] + ";"
        if _START.match(m):
            stmt_is_insert = _START.match(m).group(1).upper() == "INSERT"
        out.append(orig)
        if m.strip():
            prev_masked = m
    return "\n".join(out)


def _structure(batch: Batch, statements, mode: str) -> list[Finding]:
    f: list[Finding] = []
    base = batch.start_line

    def line_of(node) -> int:
        for ident in node.find_all(exp.Identifier, exp.Star, exp.Var, exp.Literal):
            ln = ident.meta.get("line") if hasattr(ident, "meta") else None
            if ln:
                return base + ln - 1
        return base

    def snippet(node) -> str:
        try:
            return node.sql(dialect="tsql")[:90]
        except Exception:  # pragma: no cover
            return ""

    for stmt in statements:
        if stmt is None:
            continue
        ctes = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}
        for node in stmt.walk():
            if isinstance(node, (exp.Update, exp.Delete)) and not node.args.get("where"):
                kind = "UPDATE" if isinstance(node, exp.Update) else "DELETE"
                f.append(Finding("TG-W002", Severity.BLOCK, line_of(node),
                                 f"{kind} without WHERE touches every row", snippet(node)))
            elif isinstance(node, exp.Select):
                for proj in node.expressions:
                    is_star = isinstance(proj, exp.Star) or (isinstance(proj, exp.Column) and isinstance(proj.this, exp.Star))
                    if is_star and not node.find_ancestor(exp.Exists):
                        f.append(Finding("TG-Q001", Severity.WARN, line_of(proj),
                                         "SELECT * : list the columns", snippet(node)))
                if node.args.get("into"):
                    pass  # TG-W004 is reported by the keyword scan
            elif isinstance(node, exp.Table):
                tname = node.name
                if not tname or tname.startswith(("#", "@")) or snippet(node).startswith(("#", "@")):
                    continue  # temp tables and table variables have no schema
                if isinstance(node.this, exp.Func) or isinstance(node.this, exp.Anonymous):
                    continue
                if node.find_ancestor(exp.Execute, exp.ExecuteSql):
                    continue  # EXEC <procedure>: reported by TG-E001, not a table
                if node.args.get("db") is None and tname.lower() not in ctes:
                    # the target of an UPDATE/DELETE alias (UPDATE o SET ... FROM Sales.Orders o) is an alias, not a table
                    if _is_alias_target(node, stmt):
                        continue
                    f.append(Finding("TG-Q002", Severity.WARN, line_of(node),
                                     f"table '{tname}' has no schema", snippet(node)))
    return f


def _is_alias_target(node: exp.Table, stmt: exp.Expression) -> bool:
    aliases = {t.alias.lower() for t in stmt.find_all(exp.Table) if t.alias}
    return node.name.lower() in aliases and isinstance(node.parent, (exp.Update, exp.Delete))


# --- public API ----------------------------------------------------------------------------------------------------


def check_text(text: str, mode: str = "readonly", _depth: int = 0) -> list[Finding]:
    if mode not in {"readonly", "readwrite"}:
        raise ValueError("mode must be 'readonly' or 'readwrite'")
    findings: list[Finding] = []
    for batch in split_batches(text):
        masked = mask(batch.text)
        findings.extend(_keyword_scan(batch, masked, mode, _depth))
        parsed = _parse(batch.text)
        if parsed is None:
            findings.append(Finding("TG-P001", Severity.BLOCK, batch.start_line,
                                    "could not parse this batch (fails closed): review it by hand",
                                    _snippet(batch.text, 0)))
        else:
            findings.extend(_structure(batch, parsed, mode))
    # one finding per rule+line+message
    seen, unique = set(), []
    for x in findings:
        key = (x.rule, x.line, x.message)
        if key not in seen:
            seen.add(key)
            unique.append(x)
    unique.sort(key=lambda x: (x.line, x.rule))
    return unique


def check_file(path: str | Path, mode: str = "readonly") -> list[Finding]:
    return check_text(Path(path).read_text(encoding="utf-8-sig"), mode=mode)


def exit_code(findings: list[Finding]) -> int:
    if any(f.severity == Severity.BLOCK for f in findings):
        return 2
    if any(f.severity == Severity.WARN for f in findings):
        return 1
    return 0
