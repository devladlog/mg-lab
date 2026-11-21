"""Read SQL Server XML showplans (what SET STATISTICS XML returns, or a .sqlplan file from SSMS).

Only the parts an index review needs:

* every data-access operator (scan, seek, lookup) with its table and index, estimated and actual rows,
  executions, logical reads and execution mode (Row or Batch);
* "pages read" for the whole statement: the sum of ActualLogicalReads + ActualLobLogicalReads over all
  operators and threads (columnstore reads are reported as LOB reads, like SET STATISTICS IO does);
* the optimizer's missing index requests, turned into a CREATE INDEX statement the way Learn describes
  (equality columns, then inequality columns, then INCLUDE) - for review, not to run blindly;
* plan warnings (implicit conversions, spills, no join predicate) and parameter values: the value the
  plan was compiled for versus the value it ran with.

Element and attribute names come from the showplan schema
(http://schemas.microsoft.com/sqlserver/2004/07/showplan, sql2022/showplanxml.xsd).

    python src/showplan.py plans/customer-orders-1.sqlplan     # print a summary
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

NS = {"p": "http://schemas.microsoft.com/sqlserver/2004/07/showplan"}
_P = "{" + NS["p"] + "}"

# Physical operators that read a table or an index.
ACCESS_OPS = {
    "Clustered Index Scan", "Clustered Index Seek", "Index Scan", "Index Seek", "Table Scan",
    "Key Lookup", "RID Lookup", "Columnstore Index Scan",
}


def _unbracket(name: str | None) -> str | None:
    if name is None:
        return None
    return name[1:-1] if name.startswith("[") and name.endswith("]") else name


def _unparen(value: str | None) -> str | None:
    if value is None:
        return None
    return value[1:-1] if value.startswith("(") and value.endswith(")") else value


@dataclass
class Operator:
    node_id: int
    physical_op: str
    logical_op: str
    estimate_rows: float
    table: str | None = None          # schema.table, no brackets
    index: str | None = None
    index_kind: str | None = None     # Clustered / NonClustered / Heap ...
    storage: str | None = None        # RowStore / ColumnStore
    lookup: bool = False
    actual_rows: int | None = None    # summed over threads; None in an estimated plan
    actual_executions: int | None = None
    logical_reads: int = 0
    lob_logical_reads: int = 0
    execution_mode: str | None = None  # actual if present, else estimated
    warnings: list[str] = field(default_factory=list)

    @property
    def is_access(self) -> bool:
        return self.physical_op in ACCESS_OPS

    @property
    def is_columnstore(self) -> bool:
        return self.physical_op == "Columnstore Index Scan" or self.storage == "ColumnStore"

    @property
    def label(self) -> str:
        name = "Key Lookup" if self.lookup and self.physical_op != "RID Lookup" else self.physical_op
        return f"{name}({self.index})" if self.index else name


@dataclass
class MissingIndex:
    database: str
    schema: str
    table: str
    impact: float
    equality: list[str]
    inequality: list[str]
    include: list[str]

    def to_create_index(self, name: str | None = None) -> str:
        """CREATE INDEX text in Learn's order: equality columns, then inequality columns, then INCLUDE.

        Learn: the suggestion doesn't specify an order for the key columns; order equality columns by
        selectivity yourself. Review it against existing indexes before creating anything.
        """
        keys = self.equality + self.inequality
        name = name or "IX_" + self.table + "_" + "_".join(keys)
        sql = (f"CREATE NONCLUSTERED INDEX [{name}] ON [{self.schema}].[{self.table}] "
               f"({', '.join(f'[{c}]' for c in keys)})")
        if self.include:
            sql += f" INCLUDE ({', '.join(f'[{c}]' for c in self.include)})"
        return sql + ";"


@dataclass
class Parameter:
    name: str
    data_type: str | None
    compiled_value: str | None
    runtime_value: str | None


@dataclass
class StatementPlan:
    text: str
    operators: list[Operator]
    missing_indexes: list[MissingIndex]
    warnings: list[str]
    parameters: list[Parameter]
    has_dispatcher: bool = False      # Parameter Sensitive Plan optimization dispatcher (SQL Server 2022+)
    query_variant_id: int | None = None
    cpu_ms: int | None = None
    elapsed_ms: int | None = None
    is_actual: bool = False
    optimization_level: str | None = None   # TRIVIAL or FULL; no missing index requests for TRIVIAL plans

    @property
    def pages_read(self) -> int:
        return sum(o.logical_reads + o.lob_logical_reads for o in self.operators)

    def find(self, physical_op: str, index: str | None = None) -> list[Operator]:
        """Operators by physical name. 'Key Lookup' also matches an IndexScan marked Lookup="true"."""
        out = []
        for o in self.operators:
            name_ok = o.physical_op == physical_op or (physical_op == "Key Lookup" and o.lookup)
            if physical_op == "Columnstore Index Scan":
                name_ok = o.is_columnstore
            if name_ok and (index is None or (o.index or "").lower() == index.lower()):
                out.append(o)
        return out

    def has(self, physical_op: str, index: str | None = None) -> bool:
        return bool(self.find(physical_op, index))

    def access_summary(self) -> str:
        """'Index Seek(IX_A) + Key Lookup(PK_B)': the data-access operators, in plan order."""
        parts = [o.label for o in self.operators if o.is_access]
        if any(o.physical_op == "Sort" for o in self.operators):
            parts.append("Sort")
        return " + ".join(parts) if parts else "(no table access)"


# ---------------------------------------------------------------- parsing
def _int_attr(el: ET.Element, name: str) -> int | None:
    v = el.get(name)
    return int(v) if v is not None else None


def _warnings(el: ET.Element | None) -> list[str]:
    if el is None:
        return []
    out = []
    for name in ("NoJoinPredicate", "SpatialGuess", "UnmatchedIndexes"):
        if el.get(name) in ("true", "1"):
            out.append(name)
    for child in el:
        tag = child.tag.replace(_P, "")
        if tag == "PlanAffectingConvert":
            out.append(f"PlanAffectingConvert {child.get('ConvertIssue')}: {child.get('Expression')}")
        else:
            out.append(tag)
    return out


def _operator(relop: ET.Element) -> Operator:
    op = Operator(
        node_id=int(relop.get("NodeId", "-1")),
        physical_op=relop.get("PhysicalOp", ""),
        logical_op=relop.get("LogicalOp", ""),
        estimate_rows=float(relop.get("EstimateRows", "0")),
        execution_mode=relop.get("EstimatedExecutionMode"),
    )
    # the operator's own child element (IndexScan, TableScan, ...) holds the object it reads
    for child in relop:
        tag = child.tag.replace(_P, "")
        if tag in ("IndexScan", "TableScan"):
            obj = child.find("p:Object", NS)
            if obj is not None:
                schema, table = _unbracket(obj.get("Schema")), _unbracket(obj.get("Table"))
                op.table = f"{schema}.{table}" if schema else table
                op.index = _unbracket(obj.get("Index"))
                op.index_kind = obj.get("IndexKind")
                op.storage = obj.get("Storage") or child.get("Storage")
            op.storage = child.get("Storage") or op.storage
            op.lookup = child.get("Lookup") in ("true", "1")
    op.warnings = _warnings(relop.find("p:Warnings", NS))
    rti = relop.find("p:RunTimeInformation", NS)
    if rti is not None:
        threads = rti.findall("p:RunTimeCountersPerThread", NS)
        op.actual_rows = sum(int(t.get("ActualRows", "0")) for t in threads)
        op.actual_executions = sum(int(t.get("ActualExecutions", "0")) for t in threads)
        op.logical_reads = sum(int(t.get("ActualLogicalReads", "0")) for t in threads)
        op.lob_logical_reads = sum(int(t.get("ActualLobLogicalReads", "0")) for t in threads)
        modes = {t.get("ActualExecutionMode") for t in threads if t.get("ActualExecutionMode")}
        if modes:
            op.execution_mode = "Batch" if "Batch" in modes else "Row"
    return op


def _missing(qp: ET.Element) -> list[MissingIndex]:
    out = []
    for group in qp.findall("p:MissingIndexes/p:MissingIndexGroup", NS):
        for mi in group.findall("p:MissingIndex", NS):
            cols = {"EQUALITY": [], "INEQUALITY": [], "INCLUDE": []}
            for cg in mi.findall("p:ColumnGroup", NS):
                cols[cg.get("Usage")] = [_unbracket(c.get("Name")) for c in cg.findall("p:Column", NS)]
            out.append(MissingIndex(
                database=_unbracket(mi.get("Database")), schema=_unbracket(mi.get("Schema")),
                table=_unbracket(mi.get("Table")), impact=float(group.get("Impact", "0")),
                equality=cols["EQUALITY"], inequality=cols["INEQUALITY"], include=cols["INCLUDE"]))
    return out


def parse_showplan(xml_text: str) -> list[StatementPlan]:
    """One StatementPlan per statement that has a query plan (or a PSP dispatcher)."""
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text)   # SSMS saves .sqlplan as UTF-16 with a declaration
    root = ET.fromstring(xml_text)
    if root.tag != _P + "ShowPlanXML":
        raise ValueError(f"not a showplan document: root element is {root.tag}")
    plans = []
    for stmt in root.iter(_P + "StmtSimple"):
        qp = stmt.find("p:QueryPlan", NS)
        dispatcher = stmt.find("p:Dispatcher", NS)
        if qp is None and dispatcher is None:
            continue
        operators, missing, warnings, params = [], [], [], []
        cpu = elapsed = variant = None
        actual = False
        if qp is not None:
            operators = [_operator(r) for r in qp.iter(_P + "RelOp")]
            missing = _missing(qp)
            warnings = _warnings(qp.find("p:Warnings", NS))
            for cr in qp.findall("p:ParameterList/p:ColumnReference", NS):
                params.append(Parameter(cr.get("Column"), cr.get("ParameterDataType"),
                                        _unparen(cr.get("ParameterCompiledValue")),
                                        _unparen(cr.get("ParameterRuntimeValue"))))
            ts = qp.find("p:QueryTimeStats", NS)
            if ts is not None:
                cpu, elapsed = _int_attr(ts, "CpuTime"), _int_attr(ts, "ElapsedTime")
            variant = _int_attr(qp, "QueryVariantID")
            actual = qp.find(".//p:RunTimeInformation", NS) is not None
        plans.append(StatementPlan(
            text=stmt.get("StatementText", "").strip(), operators=operators, missing_indexes=missing,
            warnings=warnings, parameters=params, has_dispatcher=dispatcher is not None,
            query_variant_id=variant, cpu_ms=cpu, elapsed_ms=elapsed, is_actual=actual,
            optimization_level=stmt.get("StatementOptmLevel")))
    return plans


def read_plan_file(path: str | Path) -> str:
    """Text of a .sqlplan / .xml file: UTF-16 (how SSMS saves them) or UTF-8."""
    data = Path(path).read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def describe(plan: StatementPlan) -> str:
    lines = [f"statement : {plan.text[:100]}",
             f"optimized : {plan.optimization_level or 'n/a'}",
             f"access    : {plan.access_summary()}",
             f"pages read: {plan.pages_read if plan.is_actual else 'n/a (estimated plan)'}"]
    for o in plan.operators:
        if o.is_access:
            rows = "" if o.actual_rows is None else f" actual {o.actual_rows} rows x{o.actual_executions}"
            lines.append(f"  node {o.node_id:>2} {o.label:<55} est {o.estimate_rows:g}{rows}"
                         f" reads {o.logical_reads + o.lob_logical_reads} {o.execution_mode or ''}".rstrip())
    for p in plan.parameters:
        lines.append(f"parameter : {p.name} {p.data_type} compiled={p.compiled_value} runtime={p.runtime_value}")
    for w in plan.warnings + [w for o in plan.operators for w in o.warnings]:
        lines.append(f"warning   : {w}")
    for mi in plan.missing_indexes:
        lines.append(f"missing   : impact {mi.impact:.1f}%  {mi.to_create_index()}")
    if plan.has_dispatcher or plan.query_variant_id is not None:
        lines.append(f"PSP       : dispatcher={plan.has_dispatcher} query variant={plan.query_variant_id}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        for plan in parse_showplan(read_plan_file(path)):
            print(f"-- {path}\n{describe(plan)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
