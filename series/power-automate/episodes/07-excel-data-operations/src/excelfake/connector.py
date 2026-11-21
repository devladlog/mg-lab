"""The Excel Online (Business) connector, in memory, with the behaviours Learn documents.

Documented (Excel Online (Business) connector reference, known issues):
- List rows present in a table returns up to 256 rows by default; turn on pagination to get all rows.
- Column names in results are encoded for OData: "." -> _x002e_, "@" -> _x0040_, ":" -> _x003a_, "#" -> _x0023_.
- The key column field is case-sensitive; Update a row / Delete a row change only the first match.
- 100 API calls per connection per 60 seconds; Run script 3 calls per 10 seconds and 1,600 per day.
- Maximum request size 5 MB. Run script parameters at most 30,000,000 bytes (Office Scripts limits).
- Pagination (connectors known issues + Logic Apps pagination article): the engine keeps calling until it has
  all items or reaches the threshold, page by page, so it can return more than the threshold. Each page is a
  request (Power Automate limits: "requests from pagination also count as action runs").

Assumed, not documented (demo.md checks them against a real run):
- the page size with pagination on is also 256;
- values come back as text: numbers in invariant format ("12.5"), dates as the serial number ("46357")
  unless DateTime Format is "ISO 8601" ("2026-12-01T00:00:00.000Z").

It's a test double. The Run script action really runs the Office Script (TypeScript) through
officescript/run-script.mjs with Node.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .workbook import ExcelDate, Table, Workbook

PAGE_SIZE = 256
CALLS_PER_MINUTE = 100
RUN_SCRIPT_PER_DAY = 1600
MAX_REQUEST_BYTES = 5 * 1024 * 1024
MAX_SCRIPT_PARAM_BYTES = 30_000_000
MAX_PAGINATION_THRESHOLD = 100_000
RUNNER = Path(__file__).resolve().parents[1] / "officescript" / "run-script.mjs"

ENCODE = {".": "_x002e_", "@": "_x0040_", ":": "_x003a_", "#": "_x0023_"}


def encode_column(name: str) -> str:
    for ch, code in ENCODE.items():
        name = name.replace(ch, code)
    return name


def as_text(value, iso_dates: bool) -> str:
    if value is None:
        return ""
    if isinstance(value, ExcelDate):
        if iso_dates:
            return value.to_date().isoformat() + "T00:00:00.000Z"
        return str(int(value.serial))
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class ExcelError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Excel:
    """Files (by file id) shared by every connection; one call log per run."""
    files: dict[str, Workbook] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    script_calls: int = 0
    runner: Path = RUNNER

    def put(self, file_id: str, wb: Workbook):
        self.files[file_id] = wb

    def _table(self, p: dict) -> Table:
        wb = self.files.get(p.get("file"))
        if wb is None:
            raise ExcelError(404, f"File not found: {p.get('file')!r}")
        t = wb.tables.get(p.get("table"))
        if t is None:
            raise ExcelError(400, f"No table named {p.get('table')!r} in {wb.name} (the connector needs an Excel table)")
        return t

    def _call(self, op: str, p: dict):
        if len(json.dumps(p, default=str).encode()) > MAX_REQUEST_BYTES:
            raise ExcelError(413, "The maximum supported size of each connector request is 5 MB")
        self.calls.append(op)

    @property
    def minimum_minutes(self) -> int:
        """Minutes the calls need at 100 calls per connection per 60 seconds."""
        return math.ceil(len(self.calls) / CALLS_PER_MINUTE)

    # ------------------------------------------------------------------ operations
    def get_items(self, p: dict, threshold: int | None = None) -> dict:
        t = self._table(p)
        if any(p.get(k) for k in ("$filter", "$orderby", "$select")):
            raise ExcelError(400, "excelfake doesn't implement Filter Query / Order By / Select Query")
        iso = str(p.get("dateTimeFormat", "")).upper().startswith("ISO")
        rows = t.rows
        skip = int(p.get("$skip") or 0)
        rows = rows[skip:]
        if p.get("$top"):
            rows = rows[: int(p["$top"])]
        if threshold is None:
            pages = 1
            rows = rows[:PAGE_SIZE]
        else:
            if not 1 <= threshold <= MAX_PAGINATION_THRESHOLD:
                raise ExcelError(400, f"pagination threshold must be 1-{MAX_PAGINATION_THRESHOLD}")
            pages = max(1, math.ceil(min(len(rows), math.ceil(threshold / PAGE_SIZE) * PAGE_SIZE) / PAGE_SIZE))
            rows = rows[: pages * PAGE_SIZE]
        for _ in range(pages):
            self._call("GetItems", p)
        names = [encode_column(h) for h in t.headers]
        return {"value": [{n: as_text(v, iso) for n, v in zip(names, r)} for r in rows]}

    def _key(self, t: Table, p: dict) -> int:
        col = p.get("idColumn")
        if col not in t.headers:  # case-sensitive (Learn)
            raise ExcelError(400, f"Key column {col!r} wasn't found (the key column field is case-sensitive)")
        return t.column(col)

    def get_item(self, p: dict) -> dict:
        self._call("GetItem", p)
        t = self._table(p)
        ci = self._key(t, p)
        for r in t.rows:
            if as_text(r[ci], False) == str(p.get("id")):
                return {encode_column(h): as_text(v, False) for h, v in zip(t.headers, r)}
        raise ExcelError(404, f"No row with {p.get('idColumn')} = {p.get('id')!r}")

    def patch_item(self, p: dict) -> dict:
        self._call("PatchItem", p)
        t = self._table(p)
        ci = self._key(t, p)
        item = p.get("item") or {}
        for r in t.rows:  # only the first match is updated (Learn)
            if as_text(r[ci], False) == str(p.get("id")):
                for k, v in item.items():
                    if k in t.headers:
                        r[t.column(k)] = v
                return {encode_column(h): as_text(v, False) for h, v in zip(t.headers, r)}
        raise ExcelError(404, f"No row with {p.get('idColumn')} = {p.get('id')!r}")

    def add_row(self, p: dict) -> dict:
        self._call("AddRowV2", p)
        t = self._table(p)
        item = p.get("item") or {}
        t.rows.append([item.get(h) for h in t.headers])
        return {encode_column(h): as_text(item.get(h), False) for h in t.headers}

    def run_script(self, p: dict) -> dict:
        """Run script from SharePoint library: one call, the script does the work in the workbook."""
        self._call("RunScriptProdV2", p)
        self.script_calls += 1
        if self.script_calls > RUN_SCRIPT_PER_DAY:
            raise ExcelError(429, "Run script: 1,600 calls per user per day")
        params = {k.split("/", 1)[1]: v for k, v in p.items() if k.startswith("ScriptParameters/")}
        if len(json.dumps(params).encode()) > MAX_SCRIPT_PARAM_BYTES:
            raise ExcelError(400, "Run script parameters are limited to 30,000,000 bytes")
        wb = self.files.get(p.get("file"))
        if wb is None:
            raise ExcelError(404, f"File not found: {p.get('file')!r}")
        stem = Path(str(p.get("scriptId", "Upsert prices.osts"))).stem  # "Upsert prices" -> UpsertPrices.ts
        script = "".join(w[:1].upper() + w[1:] for w in stem.split()) + ".ts"
        out = run_office_script(self.runner, script, wb, [params.get("prices"), params.get("supplier"),
                                                          params.get("sourceFile")])
        if not out["ok"]:
            raise ExcelError(400, f"Office Script error: {out['error']}")
        for name, t in out["tables"].items():
            wb.tables[name].rows = [[_from_json(c) for c in r] for r in t["rows"]]
        return {"result": out["result"], "logs": out["logs"], "writes": out["writes"]}


def _to_json(v):
    if isinstance(v, ExcelDate):
        return v.serial
    return v


def _from_json(v):
    return v


def run_office_script(runner: Path, script: str, wb: Workbook, args: list) -> dict:
    node = shutil.which("node")
    if node is None:
        raise ExcelError(500, "node isn't installed: excelfake runs Office Scripts with Node 22.13+")
    req = {"script": script, "args": args,
           "tables": {n: {"headers": t.headers, "rows": [[_to_json(c) for c in r] for r in t.rows]}
                      for n, t in wb.tables.items()}}
    proc = subprocess.run([node, "--no-warnings", str(runner)], input=json.dumps(req), capture_output=True,
                          text=True, timeout=150)
    if proc.returncode != 0:
        raise ExcelError(500, f"run-script.mjs failed: {proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout)
