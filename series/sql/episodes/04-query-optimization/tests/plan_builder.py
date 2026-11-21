"""Build small showplan XML documents for the tests.

The real plans come from SQL Server during the recording (index_lab.py --save-plans). The build
container has no SQL Server, so the tests build plans with the same elements and attributes and, when the
official schema file is available, validate every document against it (test_plans_are_schema_valid):

    mkdir -p tests/.xsd && curl -o tests/.xsd/showplanxml.xsd \
        https://schemas.microsoft.com/sqlserver/2004/07/showplan/sql2022/showplanxml.xsd

Element order follows the schema: RelOp = OutputList, Warnings?, RunTimeInformation?, <operator>;
QueryPlan = MissingIndexes?, Warnings?, QueryTimeStats?, RelOp, ParameterList?.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

NS = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"
DB, SCHEMA = "[ContosoBikesPerf]", "[Sales]"


@dataclass
class Op:
    physical: str
    logical: str
    est_rows: float
    children: list["Op"] = field(default_factory=list)
    table: str | None = None           # e.g. "Orders" for data-access operators
    index: str | None = None
    index_kind: str = "NonClustered"
    lookup: bool = False
    storage: str | None = None         # "ColumnStore" for a columnstore scan
    actual: tuple | None = None        # (rows, executions, logical_reads, lob_reads, mode) per thread 0
    est_mode: str = "Row"
    warnings_xml: str = ""


def _a(**kw) -> str:
    return "".join(f" {k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def _relop(op: Op, ids: list[int]) -> str:
    node = ids[0]
    ids[0] += 1
    out = (f"<RelOp{_a(NodeId=node, PhysicalOp=op.physical, LogicalOp=op.logical, EstimateRows=op.est_rows, EstimateIO=0.01, EstimateCPU=0.001, AvgRowSize=20, EstimatedTotalSubtreeCost=0.5, Parallel=0, EstimateRebinds=0, EstimateRewinds=0, EstimatedExecutionMode=op.est_mode)}>"
           f"<OutputList><ColumnReference{_a(Database=DB, Schema=SCHEMA, Table='[Orders]', Column='OrderId')}/></OutputList>")
    out += op.warnings_xml
    if op.actual is not None:
        rows, execs, reads, lob, mode = op.actual
        out += ("<RunTimeInformation><RunTimeCountersPerThread"
                f"{_a(Thread=0, ActualRows=rows, ActualEndOfScans=1, ActualExecutions=execs, ActualExecutionMode=mode, ActualLogicalReads=reads if op.table else None, ActualLobLogicalReads=lob if op.table else None)}"
                "/></RunTimeInformation>")
    kids = "".join(_relop(c, ids) for c in op.children)
    if op.table:
        obj = _a(Database=DB, Schema=SCHEMA, Table=f"[{op.table}]", Index=f"[{op.index}]" if op.index else None,
                 IndexKind=op.index_kind, Storage=op.storage)
        out += (f"<IndexScan{_a(Lookup=1 if op.lookup else None, Ordered=1, ScanDirection='FORWARD', Storage=op.storage)}>"
                f"<DefinedValues/><Object{obj}/></IndexScan>")
    elif op.physical == "Nested Loops":
        out += f"<NestedLoops Optimized=\"0\">{kids}</NestedLoops>"
    elif op.physical == "Sort":
        out += ("<Sort Distinct=\"0\"><OrderBy><OrderByColumn Ascending=\"0\">"
                f"<ColumnReference{_a(Database=DB, Schema=SCHEMA, Table='[Orders]', Column='OrderDate')}/>"
                f"</OrderByColumn></OrderBy>{kids}</Sort>")
    elif op.physical == "Hash Match":
        out += f"<Hash>{kids}</Hash>"
    elif op.physical == "Compute Scalar":
        out += f"<ComputeScalar>{kids}</ComputeScalar>"
    elif op.physical == "Stream Aggregate":
        out += f"<StreamAggregate>{kids}</StreamAggregate>"
    else:
        raise ValueError(f"builder has no element for {op.physical}")
    return out + "</RelOp>"


def missing_index_xml(impact: float, equality=(), inequality=(), include=()) -> str:
    groups = ""
    col_id = iter(range(1, 50))
    for usage, cols in (("EQUALITY", equality), ("INEQUALITY", inequality), ("INCLUDE", include)):
        if cols:
            groups += f"<ColumnGroup Usage=\"{usage}\">" + "".join(
                f"<Column{_a(Name=f'[{c}]', ColumnId=next(col_id))}/>" for c in cols) + "</ColumnGroup>"
    return (f"<MissingIndexes><MissingIndexGroup Impact=\"{impact}\">"
            f"<MissingIndex{_a(Database=DB, Schema=SCHEMA, Table='[Orders]')}>{groups}</MissingIndex>"
            "</MissingIndexGroup></MissingIndexes>")


def plan_xml(root: Op, text: str = "SELECT ...", missing_xml: str = "", warnings_xml: str = "",
             params: list[tuple] = (), cpu_ms: int | None = 12, elapsed_ms: int | None = 15,
             variant: int | None = None, dispatcher_xml: str = "", level: str = "FULL") -> str:
    """params: (name, type, compiled, runtime) - values written the way SQL Server does: '(4242)'."""
    stats = f"<QueryTimeStats{_a(CpuTime=cpu_ms, ElapsedTime=elapsed_ms)}/>" if cpu_ms is not None else ""
    plist = ""
    if params:
        plist = "<ParameterList>" + "".join(
            f"<ColumnReference{_a(Column=n, ParameterDataType=t, ParameterCompiledValue=c, ParameterRuntimeValue=r)}/>"
            for n, t, c, r in params) + "</ParameterList>"
    qp = (f"<QueryPlan{_a(DegreeOfParallelism=1, CachedPlanSize=40, CompileTime=2, CompileCPU=2, CompileMemory=300, QueryVariantID=variant)}>"
          f"{missing_xml}{warnings_xml}{stats}{_relop(root, [0])}{plist}</QueryPlan>")
    return (f"<?xml version=\"1.0\" encoding=\"utf-16\"?>"
            f"<ShowPlanXML xmlns=\"{NS}\" Version=\"1.564\" Build=\"16.0.4000.0\"><BatchSequence><Batch><Statements>"
            f"<StmtSimple{_a(StatementText=text, StatementId=1, StatementCompId=1, StatementType='SELECT', StatementOptmLevel=level)}>"
            f"{dispatcher_xml}{qp}</StmtSimple></Statements></Batch></BatchSequence></ShowPlanXML>")


# ---------------------------------------------------------------- the episode's plans, as SQL Server is expected to run them
def scan(index="PK_Orders", rows=7, reads=10420, kind="Clustered", physical="Clustered Index Scan",
         table="Orders", est=7.0):
    logical = "Clustered Index Scan" if physical == "Clustered Index Scan" else "Index Scan"
    return Op(physical, logical, est, table=table, index=index, index_kind=kind, actual=(rows, 1, reads, 0, "Row"))


def seek(index, rows=7, reads=3, table="Orders", est=7.0):
    return Op("Index Seek", "Index Seek", est, table=table, index=index, actual=(rows, 1, reads, 0, "Row"))


def key_lookup(rows=7, reads=21, execs=7):
    return Op("Key Lookup", "Key Lookup", 1.0, table="Orders", index="PK_Orders", index_kind="Clustered",
              lookup=True, actual=(rows, execs, reads, 0, "Row"))


def sort(child, rows=7):
    return Op("Sort", "Sort", rows, [child], actual=(rows, 1, 0, 0, "Row"))


def nested_loops(outer, inner, rows=7):
    return Op("Nested Loops", "Inner Join", rows, [outer, inner], actual=(rows, 1, 0, 0, "Row"))


def aggregate(child):
    return Op("Stream Aggregate", "Aggregate", 1, [child], actual=(1, 1, 0, 0, "Row"))


CONVERT = ('<Warnings><PlanAffectingConvert ConvertIssue="Seek Plan" '
           'Expression="CONVERT_IMPLICIT(int,[ContosoBikesPerf].[Sales].[Customers].[AccountNumber],0)=[@1]"/></Warnings>')
P = "@CustomerId"
BIG, SMALL = 60000, 7

SARGABLE = {
    "function on column": plan_xml(aggregate(scan("IX_Orders_OrderDate", rows=4856, reads=716, kind="NonClustered",
                                                  physical="Index Scan", est=1000))),
    "date range": plan_xml(aggregate(seek("IX_Orders_OrderDate", rows=4856, reads=20, est=4856))),
}

CONVERSION = {
    "int literal": plan_xml(scan("UX_Customers_AccountNumber", rows=1, reads=58, kind="NonClustered",
                                 physical="Index Scan", table="Customers", est=1), warnings_xml=CONVERT),
    "varchar literal": plan_xml(seek("UX_Customers_AccountNumber", rows=1, reads=2, table="Customers", est=1)),
}


def _scan_plan(compiled, runtime, rows):
    return plan_xml(sort(scan(rows=rows, est=BIG), rows), params=[(P, "int", f"({compiled})", f"({runtime})")])


def _seek_plan(compiled, runtime, rows):
    return plan_xml(sort(nested_loops(seek("IX_Orders_CustomerId", rows=rows, reads=2 + rows // 400, est=SMALL),
                                      key_lookup(rows=rows, reads=3 * rows, execs=rows), rows), rows),
                    params=[(P, "int", f"({compiled})", f"({runtime})")])


SNIFFING = {
    "Megastore first": _scan_plan(1, 1, BIG),
    "then customer 4242": _scan_plan(1, 4242, SMALL),
    "4242 first": _seek_plan(4242, 4242, SMALL),
    "then Megastore": _seek_plan(4242, 1, BIG),
    "RECOMPILE, 4242": plan_xml(sort(nested_loops(seek("IX_Orders_CustomerId", reads=2),
                                                  key_lookup()))),
    "RECOMPILE, Megastore": plan_xml(sort(scan(rows=BIG, est=BIG), BIG)),
}

QUERY_STORE = {
    "forced plan, 4242 first": _scan_plan(4242, 4242, SMALL),
    "forced plan, Megastore": _scan_plan(4242, 1, BIG),
}
