"""Tests for the Query Optimization episode.

1. Data, rewrites and the procedure's query run locally on DuckDB (T-SQL transpiled by sqlglot) and are
   compared with an independent Python computation and with expected/: every rewrite returns exactly what
   the original returns.
2. The checks ("Index Seek on ...", "warning: PlanAffectingConvert", "compiled: 4242") are evaluated against
   showplans built with the schema's elements (plan_builder.py), including plans that must FAIL them.
3. The SQL Server run (plan cache, sp_recompile, Query Store forcing) is exercised end to end against a
   fake connection that behaves like the plan cache. That proves the orchestration only; the real
   plans come from the recording on CON-SQL01.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import labdb  # noqa: E402
import plan_builder as pb  # noqa: E402
import showplan  # noqa: E402
import tune_lab as lab  # noqa: E402

SQL = ROOT / "src" / "sql"


def model_orders():
    for v in range(1, 200_001):
        yield {"OrderId": v,
               "CustomerId": 1 if v % 10 < 3 else 2 + (v * 7919) % 19999,
               "OrderDate": dt.date(2023, 1, 1) + dt.timedelta(days=(v * 13) % 1277),
               "TotalAmount": Decimal(5) + Decimal((v * 37) % 50000) / 100}


@pytest.fixture(scope="module")
def orders():
    return list(model_orders())


@pytest.fixture(scope="module")
def db():
    engine = labdb.DuckDBEngine()
    labdb.run_script(engine, SQL / lab.SETUP_FILE)
    yield engine
    engine.close()


def rows(db, sql):
    return db.query(lab.sql_text(sql))[1]


# ---------------------------------------------------------------- rewrites return the same answer
def test_sargable_rewrite_returns_the_same_as_the_function(db, orders):
    march = [o for o in orders if o["OrderDate"].year == 2025 and o["OrderDate"].month == 3]
    want = [(len(march), sum(o["TotalAmount"] for o in march))]
    assert rows(db, "q01a-function-on-column.sql") == rows(db, "q01b-date-range.sql") == want
    assert want[0][0] == 4856


def test_matching_type_returns_the_same_customer(db):
    assert rows(db, "q02a-implicit-conversion.sql") == rows(db, "q02b-matching-type.sql") == [(4242, "104242")]


@pytest.mark.parametrize("customer,count", [(1, 60_000), (4242, 7)])
def test_procedure_query_matches_the_model(db, orders, customer, count):
    mine = sorted((o for o in orders if o["CustomerId"] == customer),
                  key=lambda o: (o["OrderDate"], o["OrderId"]), reverse=True)
    cols, got = db.query(lab.proc_query(customer))
    assert cols == ["OrderId", "OrderDate", "Status", "TotalAmount", "ShipCountry"]
    assert [r[0] for r in got] == [o["OrderId"] for o in mine] and len(got) == count
    assert lab.proc_summary(customer, cols, got)[1][2] == f"{sum(o['TotalAmount'] for o in mine):.2f}"
    assert lab.check_result(f"proc:{customer}", cols, got) == []


def test_both_procedures_run_the_same_query():
    text = (SQL / lab.PROC_FILE).read_text()
    bodies = re.findall(r"SET NOCOUNT ON;\s*(SELECT .*?);?\s*(?:OPTION \(RECOMPILE\);)?\s*END;", text, re.S)
    assert len(bodies) == 2
    assert bodies[0].rstrip(";").strip() == bodies[1].strip()
    assert "OPTION (RECOMPILE)" in text.split("GetCustomerOrders_Recompile")[1]


@pytest.mark.parametrize("name", lab.LOCAL_QUERIES)
def test_results_match_expected_csv(db, name):
    cols, got = db.query(lab.sql_text(name))
    assert lab.check_result(name[:-4], cols, got) == []


def test_local_run_reports_everything_green(capsys):
    assert lab.main([]) == 0
    out = capsys.readouterr().out
    assert "procedure query, customers 1 and 4242: 60000 and 7 rows" in out
    assert "rewrites return identical results: q01a = q01b True, q02a = q02b True" in out
    assert "syntax: 8/8 T-SQL files parse" in out


def test_sql_files_parse_and_sqlserver_only_files_exist():
    checked = [f for f in SQL.glob("*.sql") if f.name not in lab.SQLSERVER_ONLY]
    assert len(checked) == 8 and [e for f in checked for e in labdb.tsql_syntax_errors(f)] == []
    assert all((SQL / f).exists() for f in lab.SQLSERVER_ONLY)
    assert "PARAMETER_SENSITIVE_PLAN_OPTIMIZATION = OFF" in (SQL / "psp-off.sql").read_text()


def test_scenarios_reference_real_files_and_earlier_runs():
    for sc in lab.SCENARIOS:
        seen = []
        for run in sc.runs:
            for f in [run.sql, *run.before]:
                assert not f.endswith(".sql") or (SQL / f).exists()
            for c in run.checks:
                kind, _, arg = (s.strip() for s in c.partition(":"))
                assert kind in lab.CHECK_KINDS
                if "than" in kind:
                    assert arg in seen, f"{sc.key}/{run.name}: {c}"
            seen.append(run.name)


# ---------------------------------------------------------------- checks against plans
PLANS = {"sargable": pb.SARGABLE, "conversion": pb.CONVERSION, "sniffing": pb.SNIFFING, "query-store": pb.QUERY_STORE}


def evaluate_all(sc, plans):
    done = {}
    for run in sc.runs:
        res = lab.RunResult(run, showplan.parse_showplan(plans[run.name])[0], [])
        res.failures = [m for c in run.checks if (m := lab.evaluate(c, res, done))]
        done[run.name] = res
    return done


@pytest.mark.parametrize("sc", lab.SCENARIOS, ids=lambda s: s.key)
def test_expected_plans_pass_every_check(sc):
    assert {k: r.failures for k, r in evaluate_all(sc, PLANS[sc.key]).items() if r.failures} == {}


def test_sniffing_checks_fail_if_sql_server_picks_the_right_plan_anyway():
    # e.g. PSP optimization still on: the Megastore gets its own plan even after customer 4242 compiled it
    plans = dict(pb.SNIFFING)
    plans["then Megastore"] = pb._scan_plan(1, 1, pb.BIG)
    fails = evaluate_all(lab.SCENARIOS[2], plans)["then Megastore"].failures
    assert any("expected Key Lookup" in f for f in fails)
    assert "expected compiled @CustomerId = 4242, plan says 1" in fails
    assert any("expected more" in f for f in fails)


def test_conversion_checks_read_the_plan_warning():
    plans = {"int literal": pb.CONVERSION["varchar literal"], "varchar literal": pb.CONVERSION["int literal"]}
    res = evaluate_all(lab.SCENARIOS[1], plans)
    assert any("expected a PlanAffectingConvert warning, got none" in f for f in res["int literal"].failures)
    assert any("did not expect ['PlanAffectingConvert Seek Plan" in f for f in res["varchar literal"].failures)


def test_unknown_check_is_an_error():
    with pytest.raises(ValueError):
        lab.evaluate("perhaps: x", None, {})


@pytest.mark.skipif(not (ROOT / "tests" / ".xsd" / "showplanxml.xsd").exists(),
                    reason="official showplan XSD not downloaded (see plan_builder.py)")
@pytest.mark.parametrize("key", [f"{g}/{k}" for g, d in PLANS.items() for k in d])
def test_plans_are_schema_valid(key):
    from lxml import etree

    group, name = key.split("/", 1)
    schema = etree.XMLSchema(etree.parse(str(ROOT / "tests" / ".xsd" / "showplanxml.xsd")))
    doc = etree.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", PLANS[group][name]).encode("utf-8"))
    assert schema.validate(doc), schema.error_log.last_error


# ---------------------------------------------------------------- the SQL Server run, against a fake plan cache
class FakeCursor:
    def __init__(self, server):
        self.server, self.sets, self.description, self._rows = server, [], None, []

    def execute(self, sql):
        self.server.log.append(sql)
        self.sets = self.server.answer(sql)
        self._load()

    def _load(self):
        if self.sets:
            cols, self._rows = self.sets.pop(0)
            self.description = [(c,) for c in cols]
        else:
            self.description, self._rows = None, []

    def fetchall(self):
        return self._rows

    def nextset(self):
        if not self.sets:
            return None
        self._load()
        return True


class FakeSqlServer:
    """One cached plan per procedure, sniffed on first use; Query Store records shapes and can force one."""

    QUERY_ID = 7

    def __init__(self, duck, forced=None):
        self.duck, self.log, self.stats = duck, [], False
        self.compiled_for = None
        self.qs_plans = {}            # shape -> plan_id
        self.forced = forced          # plan_id
        self.files = {labdb.split_batches(lab.sql_text(q))[0]: q for q in lab.LOCAL_QUERIES}

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def _plan_id(self, shape):
        return self.qs_plans.setdefault(shape, len(self.qs_plans) + 1)

    def answer(self, sql):
        s = sql.strip()
        if s.startswith("SET STATISTICS XML"):
            self.stats = s.endswith("ON;")
            return []
        if "PARAMETER_SENSITIVE_PLAN_OPTIMIZATION" in s:
            return []
        if s.startswith("EXEC sp_recompile"):
            self.compiled_for = None
            return []
        if m := re.match(r"EXEC sp_query_store_force_plan @query_id = (\d+), @plan_id = (\d+);", s):
            self.forced, self.compiled_for = int(m.group(2)), None
            return []
        if s.startswith("EXEC sp_query_store_unforce_plan"):
            self.forced = None
            return []
        if "is_forced_plan = 1 AND q.object_id" in s:
            return [(["query_id", "plan_id"], [(self.QUERY_ID, self.forced)] if self.forced else [])]
        if "WITH plans AS" in s:
            return [(["QueryId", "PlanId", "PlanShape", "IsForced", "Executions", "AvgLogicalReads"],
                     [(self.QUERY_ID, pid, shape, pid == self.forced, 2, Decimal("1000.0"))
                      for shape, pid in sorted(self.qs_plans.items(), key=lambda kv: kv[1])])]
        if "force_failure_count" in s:
            return [(["PlanId", "QueryId", "ContainingObject", "ForceFailureCount", "LastForceFailureReason"],
                     [(self.forced, self.QUERY_ID, "GetCustomerOrders", 0, "NONE")] if self.forced else [])]
        if m := re.match(r"EXEC (Sales\.GetCustomerOrders(?:_Recompile)?) @CustomerId = (\d+);", s):
            customer = int(m.group(2))
            cols, data = self.duck.query(lab.proc_query(customer))
            if m.group(1).endswith("_Recompile"):
                xml = pb.SNIFFING["RECOMPILE, Megastore" if customer == 1 else "RECOMPILE, 4242"]
            else:
                if self.compiled_for is None:
                    self.compiled_for = customer
                scan_plan = (self.forced is not None and self.forced == self.qs_plans.get("clustered index scan")) \
                    or (self.forced is None and self.compiled_for == 1)
                rows_ = pb.BIG if customer == 1 else pb.SMALL
                xml = (pb._scan_plan if scan_plan else pb._seek_plan)(self.compiled_for, customer, rows_)
                self._plan_id("clustered index scan" if scan_plan else "seek + key lookup")
            sets = [(cols, data)]
            if self.stats:
                sets.append((["Microsoft SQL Server 2005 XML Showplan"], [(xml,)]))
            return sets
        q = self.files[s]
        cols, data = self.duck.query(s)
        group = pb.SARGABLE if q.startswith("q01") else pb.CONVERSION
        name = {"q01a": "function on column", "q01b": "date range", "q02a": "int literal", "q02b": "varchar literal"}[q[:4]]
        return [(cols, data)] + ([(["Microsoft SQL Server 2005 XML Showplan"], [(group[name],)])] if self.stats else [])


def test_sqlserver_run_end_to_end_against_a_fake_plan_cache(db, tmp_path):
    server = FakeSqlServer(db)
    lines = []
    code = lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, None, tmp_path, lines.append)
    text = "\n".join(lines)
    assert code == 0, text
    assert "12/12 runs behaved as expected on sqlserver" in text
    assert "EXEC sp_query_store_force_plan @query_id = 7, @plan_id = 1;" in text
    assert "plan 1 stays forced" in text
    assert "warning (int literal): PlanAffectingConvert Seek Plan" in text
    assert re.search(r"4 then Megastore\s+Sales.GetCustomerOrders @CustomerId = 1\s+Index Seek\(IX_Orders_CustomerId\) "
                     r"\+ Key Lookup\(PK_Orders\) \+ Sort\s+4242/1\s+180152\s+60000\s+OK", text)
    assert len(list(tmp_path.glob("*.sqlplan"))) == 12
    assert sum(sql == lab.RECOMPILE for sql in server.log) == 3     # two in sniffing, one before forcing


def test_a_plan_forced_by_an_earlier_run_is_unforced_first(db):
    server = FakeSqlServer(db, forced=1)
    server.qs_plans = {"clustered index scan": 1}
    lines = []
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, "sniffing", None, lines.append) == 0
    assert "   unforced plan 1 (query 7) left over from an earlier run" in lines


def test_query_store_scenario_fails_when_forcing_fails(db):
    server = FakeSqlServer(db)
    server.qs_plans = {"clustered index scan": 1, "seek + key lookup": 2}
    original = server.answer

    def failing(sql):
        sets = original(sql)
        if "force_failure_count" in sql and sets[0][1]:
            sets = [(sets[0][0], [(1, 7, "GetCustomerOrders", 3, "NO_INDEX")])]
        return sets

    server.answer = failing
    lines = []
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, "query-store", None, lines.append) == 1
    assert any("plan 1 is not forced cleanly" in ln and "NO_INDEX" in ln for ln in lines)


def test_query_store_scenario_fails_without_a_scan_plan(db):
    server = FakeSqlServer(db)                           # nothing recorded yet: no plan to force
    lines = []
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, "query-store", None, lines.append) == 1
    assert "   FAIL Query Store has no clustered index scan plan for the procedure" in lines
