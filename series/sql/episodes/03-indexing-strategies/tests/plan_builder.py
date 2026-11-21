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
         lob=0, mode="Row", storage=None, est=7.0):
    logical = "Clustered Index Scan" if physical == "Clustered Index Scan" else "Index Scan"
    return Op(physical, logical, est, table="Orders", index=index, index_kind=kind,
              actual=(rows, 1, reads, lob, mode), storage=storage, est_mode=mode)


def seek(index, rows=7, reads=3, est=7.0):
    return Op("Index Seek", "Index Seek", est, table="Orders", index=index, actual=(rows, 1, reads, 0, "Row"))


def key_lookup(rows=7, reads=21, execs=7):
    return Op("Key Lookup", "Key Lookup", 1.0, table="Orders", index="PK_Orders", index_kind="Clustered",
              lookup=True, actual=(rows, execs, reads, 0, "Row"))


def sort(child, rows=7):
    return Op("Sort", "Sort", rows, [child], actual=(rows, 1, 0, 0, "Row"))


def nested_loops(outer, inner, rows=7):
    return Op("Nested Loops", "Inner Join", rows, [outer, inner], actual=(rows, 1, 0, 0, "Row"))


CUSTOMER_ORDERS = {
    "no index": plan_xml(sort(scan()), missing_xml=missing_index_xml(98.9, equality=["CustomerId"],
                                                                      include=["OrderDate", "TotalAmount"])),
    "narrow index": plan_xml(sort(nested_loops(seek("IX_Orders_CustomerId", reads=2), key_lookup()))),
    "covering, wrong key order": plan_xml(scan("IX_Orders_OrderDate_CustomerId", reads=611, kind="NonClustered",
                                               physical="Index Scan")),
    "covering, right key order": plan_xml(seek("IX_Orders_CustomerId_OrderDate", reads=2)),
}

OPEN_ORDERS = {
    "no index": plan_xml(sort(scan(rows=49, est=49)), missing_xml=missing_index_xml(
        97.5, equality=["Status"], inequality=["OrderDate"], include=["CustomerId", "TotalAmount"])),
    "full-table index": plan_xml(seek("IX_Orders_Status_OrderDate", rows=49, reads=3)),
    "filtered index": plan_xml(seek("IX_Orders_Open", rows=49, reads=2)),
}

REVENUE_REPORT = {
    "no index": plan_xml(Op("Hash Match", "Aggregate", 12, [scan(rows=200000, est=200000, reads=10420)],
                            actual=(12, 1, 0, 0, "Row"))),
    "columnstore": plan_xml(Op("Hash Match", "Aggregate", 12, [
        scan("NCCI_Orders_Reporting", rows=200000, est=200000, reads=0, lob=410, kind="NonClustered",
             physical="Columnstore Index Scan", mode="Batch", storage="ColumnStore")],
        actual=(12, 1, 0, 0, "Batch"), est_mode="Batch")),
}
