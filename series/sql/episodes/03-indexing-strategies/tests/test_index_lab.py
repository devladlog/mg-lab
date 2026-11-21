"""Tests for the Indexing Strategies episode.

1. The data and the three queries run locally on DuckDB (T-SQL transpiled by sqlglot); every result is
   compared with an independent Python computation over the same formulas, and with expected/.
2. The scenario checks ("Index Seek on IX_...", "fewer pages than ...") are evaluated against showplans
   built with the schema's elements (plan_builder.py), including plans that must FAIL them.
3. The SQL Server run itself (drop, create, capture plan, size, compare) is exercised end to end against
   a fake connection. That proves the orchestration only; the real plans come from the recording.
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import index_lab as lab  # noqa: E402
import labdb  # noqa: E402
import plan_builder as pb  # noqa: E402

SQL = ROOT / "src" / "sql"


# ---------------------------------------------------------------- independent model of the generated data
def model_orders():
    out = []
    for v in range(1, 200_001):
        out.append({
            "OrderId": v,
            "CustomerId": 1 if v % 10 < 3 else 2 + (v * 7919) % 19999,
            "OrderDate": dt.date(2023, 1, 1) + dt.timedelta(days=(v * 13) % 1277),
            "Status": "Open" if v % 100 == 7 else "Cancelled" if v % 100 in (3, 53) else "Shipped",
            "Channel": ("Web", "Store", "Partner")[v % 3],
            "TotalAmount": Decimal(5) + Decimal((v * 37) % 50000) / 100,
        })
    return out


@pytest.fixture(scope="module")
def orders():
    return model_orders()


@pytest.fixture(scope="module")
def db():
    engine = labdb.DuckDBEngine()
    labdb.run_script(engine, SQL / lab.SETUP_FILE)
    yield engine
    engine.close()


def q(db, name):
    cols, rows = db.query((SQL / name).read_text(encoding="utf-8"))
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------- the data
def test_generated_data_matches_the_model(db, orders):
    cols, rows = db.query("SELECT OrderId, CustomerId, OrderDate, Status, Channel, TotalAmount "
                          "FROM Sales.Orders ORDER BY OrderId;")
    assert len(rows) == 200_000
    for got, want in zip(rows, orders):
        assert got == tuple(want.values())


def test_data_shape_the_episode_relies_on(orders, db):
    per_customer = Counter(o["CustomerId"] for o in orders)
    assert per_customer[1] == 60_000                       # Contoso Megastore: 30% of all orders (episode 4)
    others = [n for c, n in per_customer.items() if c != 1]
    assert len(others) == 19_999 and min(others) >= 6 and max(others) <= 8
    assert sum(o["Status"] == "Open" for o in orders) == 2_000          # 1%: the filtered index subset
    dates = [o["OrderDate"] for o in orders]
    assert (min(dates), max(dates)) == (dt.date(2023, 1, 1), dt.date(2026, 6, 30))
    assert db.query("SELECT COUNT(*) FROM Sales.Customers;")[1][0][0] == 20_000
    notes = db.query("SELECT MIN(LENGTH(Notes)), MAX(LENGTH(Notes)) FROM Sales.Orders;")[1][0]
    assert 180 <= notes[0] <= notes[1] <= 200                            # fits nvarchar(200), ~400 bytes/row


# ---------------------------------------------------------------- the three queries
def test_q01_customer_orders(db, orders):
    want = sorted((o for o in orders if o["CustomerId"] == 4242), key=lambda o: o["OrderDate"], reverse=True)
    got = q(db, "q01-customer-orders.sql")
    assert [(r["OrderId"], r["OrderDate"], r["TotalAmount"]) for r in got] == \
           [(o["OrderId"], o["OrderDate"], o["TotalAmount"]) for o in want]
    assert len(got) == 7
    assert len({o["OrderDate"] for o in want}) == len(want)   # no ties: ORDER BY OrderDate DESC is deterministic


def test_q02_open_orders(db, orders):
    want = sorted((o for o in orders if o["Status"] == "Open" and o["OrderDate"] >= dt.date(2026, 6, 1)),
                  key=lambda o: (o["OrderDate"], o["OrderId"]))
    got = q(db, "q02-open-orders.sql")
    assert [(r["OrderId"], r["CustomerId"], r["OrderDate"], r["TotalAmount"]) for r in got] == \
           [(o["OrderId"], o["CustomerId"], o["OrderDate"], o["TotalAmount"]) for o in want]
    assert len(got) == 49


def test_q03_revenue_by_year_channel(db, orders):
    agg = defaultdict(lambda: [0, Decimal(0)])
    for o in orders:
        a = agg[(o["OrderDate"].year, o["Channel"])]
        a[0] += 1
        a[1] += o["TotalAmount"]
    want = [(y, c, n, s) for (y, c), (n, s) in sorted(agg.items())]
    got = [(r["OrderYear"], r["Channel"], r["Orders"], r["Revenue"]) for r in q(db, "q03-revenue-by-year-channel.sql")]
    assert got == want and len(got) == 12


@pytest.mark.parametrize("query", [s.query for s in lab.SCENARIOS])
def test_results_match_expected_csv(db, query):
    cols, rows = db.query((SQL / query).read_text(encoding="utf-8"))
    assert lab.check_expected(query, cols, rows) == []


def test_local_run_reports_everything_green(capsys):
    assert lab.main([]) == 0
    out = capsys.readouterr().out
    assert "setup: Customers 20000, Orders 200000 (duckdb)" in out
    assert "3/3 queries match expected/ on duckdb" in out
    assert "syntax: 14/14 T-SQL files parse" in out


# ---------------------------------------------------------------- the SQL files and the scenario definitions
def test_every_sql_file_parses_as_tsql():
    files = [f for f in sorted(SQL.glob("*.sql")) if f.name not in lab.SQLSERVER_ONLY]
    assert len(files) == 14
    assert [e for f in files for e in lab.tsql_syntax_errors(f)] == []


def test_drop_file_drops_every_lab_index():
    created = {n for f in SQL.glob("ix0[1-9]*.sql") for n in lab.created_indexes(f.name)}
    dropped = set(__import__("re").findall(r"DROP INDEX IF EXISTS (\w+) ON Sales\.Orders",
                                           (SQL / lab.DROP_FILE).read_text()))
    assert created == dropped and len(created) == 6


def test_scenarios_reference_real_files_and_earlier_steps():
    for sc in lab.SCENARIOS:
        assert (SQL / sc.query).exists()
        seen = []
        for step in sc.steps:
            if step.ddl:
                assert (SQL / step.ddl).exists() and lab.created_indexes(step.ddl)
            for check in step.checks:
                kind, _, arg = (s.strip() for s in check.partition(":"))
                if "than" in kind or "of" in kind:
                    assert arg in seen, f"{sc.key}/{step.name}: '{check}' refers to a later or unknown step"
            seen.append(step.name)
    assert all((SQL / f).exists() for f in lab.FINAL_DESIGN)


def test_transpile_names_the_generate_series_column():
    out = labdb.transpile("SELECT s.value * 2 FROM GENERATE_SERIES(1, 3) AS s;")
    assert out == ["SELECT s.value * 2 FROM GENERATE_SERIES(1, 3) AS s(value)"]


def test_split_batches_on_go_lines_only():
    script = "SELECT 1;\nGO\n-- only a comment\nGO\nSELECT 'GO' AS x;\ngo\n"
    assert labdb.split_batches(script) == ["SELECT 1;", "SELECT 'GO' AS x;"]


# ---------------------------------------------------------------- checks against plans
PLANS = {"customer-orders": pb.CUSTOMER_ORDERS, "open-orders": pb.OPEN_ORDERS, "revenue-report": pb.REVENUE_REPORT}
INDEX_PAGES = {"full-table index": 1240, "filtered index": 14, "narrow index": 450,
               "covering, wrong key order": 610, "covering, right key order": 612, "columnstore": 420}


def results_for(sc, plans):
    import showplan

    done = {}
    for step in sc.steps:
        res = lab.StepResult(step, showplan.parse_showplan(plans[step.name])[0], INDEX_PAGES.get(step.name), [])
        res.failures = [m for c in step.checks if (m := lab.evaluate(c, res, done))]
        done[step.name] = res
    return done


@pytest.mark.parametrize("sc", lab.SCENARIOS, ids=lambda s: s.key)
def test_expected_plans_pass_every_check(sc):
    assert {k: r.failures for k, r in results_for(sc, PLANS[sc.key]).items() if r.failures} == {}


def test_checks_fail_when_sql_server_does_something_else():
    sc = lab.SCENARIOS[0]
    plans = dict(pb.CUSTOMER_ORDERS)
    plans["covering, right key order"] = plans["narrow index"]      # e.g. the index wasn't created
    plans["covering, wrong key order"] = plans["no index"]
    res = results_for(sc, plans)
    right = res["covering, right key order"].failures
    assert any("expected Index Seek @ IX_Orders_CustomerId_OrderDate" in f for f in right)
    assert any("did not expect Key Lookup" in f for f in right)
    assert any("did not expect Sort" in f for f in right)
    assert any("fewer" in f for f in right)                          # 23 pages is not fewer than 23
    wrong = res["covering, wrong key order"].failures
    assert any("expected Index Scan @ IX_Orders_OrderDate_CustomerId" in f for f in wrong)
    assert any("expected fewer" in f for f in wrong)                 # a full clustered scan is not "fewer"


def test_filtered_index_must_be_much_smaller():
    sc = lab.SCENARIOS[1]
    INDEX_PAGES["filtered index"] = 400
    try:
        fails = results_for(sc, pb.OPEN_ORDERS)["filtered index"].failures
    finally:
        INDEX_PAGES["filtered index"] = 14
    assert fails == ["index is 400 pages, 'full-table index' is 1240: expected below 10%"]


def test_columnstore_check_needs_batch_mode():
    import showplan

    row_mode = pb.plan_xml(pb.scan("NCCI_Orders_Reporting", rows=200000, reads=0, lob=410,
                                   physical="Columnstore Index Scan", storage="ColumnStore", mode="Row"))
    res = lab.StepResult(lab.SCENARIOS[2].steps[1], showplan.parse_showplan(row_mode)[0], 420, [])
    assert "batch mode" in lab.evaluate("batch: Columnstore Index Scan", res, {})


def test_runner_reports_a_trivial_plan_instead_of_a_missing_index(db):
    server = FakeSqlServer(db)
    original = server.answer

    def trivial(sql):
        sets = original(sql)
        if len(sets) == 2 and not server.indexes:
            xml = pb.plan_xml(pb.sort(pb.scan()), level="TRIVIAL")          # no MissingIndexes element
            sets[1] = (sets[1][0], [(xml,)])
        return sets

    server.answer = trivial
    lines = []
    assert lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, "customer-orders", None, False,
                             lines.append) == 0
    assert "   optimizer's missing index request (step 1): none (optimization level TRIVIAL)" in lines


def test_unknown_check_is_an_error():
    with pytest.raises(ValueError):
        lab.evaluate("maybe: something", None, {})


# ---------------------------------------------------------------- the SQL Server run, against a fake connection
STEP_BY_INDEXES = {
    "q01": {(): "no index", ("IX_Orders_CustomerId",): "narrow index",
            ("IX_Orders_OrderDate_CustomerId",): "covering, wrong key order",
            ("IX_Orders_CustomerId_OrderDate",): "covering, right key order"},
    "q02": {(): "no index", ("IX_Orders_Status_OrderDate",): "full-table index", ("IX_Orders_Open",): "filtered index"},
    "q03": {(): "no index", ("NCCI_Orders_Reporting",): "columnstore"},
}
QUERY_KEY = {labdb.split_batches((SQL / s.query).read_text())[0]: s.query[:3] for s in lab.SCENARIOS}
PLANS_BY_QUERY = {"q01": pb.CUSTOMER_ORDERS, "q02": pb.OPEN_ORDERS, "q03": pb.REVENUE_REPORT}


class FakeCursor:
    def __init__(self, server):
        self.server, self.sets, self.description = server, [], None

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
    """Answers like SQL Server would for the lab: real query results (from DuckDB), plans from plan_builder."""

    def __init__(self, duck):
        self.duck, self.log, self.indexes, self.stats_xml = duck, [], set(), False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def answer(self, sql):
        import re

        if sql.startswith("SET STATISTICS XML"):
            self.stats_xml = sql.endswith("ON;")
            return []
        for name in re.findall(r"DROP INDEX IF EXISTS (\w+)", sql):
            self.indexes.discard(name)
        if re.search(r"DROP INDEX|CREATE (NONCLUSTERED )?(COLUMNSTORE )?INDEX|INSERT|CREATE TABLE|SCHEMA", sql):
            self.indexes.update(lab._CREATE_INDEX.findall(sql))
            return []
        if "dm_db_partition_stats" in sql:
            rows = [("PK_Orders", "CLUSTERED", False, 200000, 10420, Decimal("81.41"))]
            rows += [(n, "NONCLUSTERED", n == "IX_Orders_Open", 1, INDEX_PAGES_BY_NAME[n], Decimal("1")) for n in sorted(self.indexes)]
            return [(["IndexName", "IndexType", "Filtered", "IndexRows", "UsedPages", "UsedMB"], rows)]
        if "dm_db_index_usage_stats" in sql:
            return [(["IndexName", "UserSeeks", "UserScans", "UserLookups", "UserUpdates"],
                     [(n, 1, 0, 0, 0) for n in ["PK_Orders", *sorted(self.indexes)]])]
        key = QUERY_KEY[sql.strip()]
        cols, rows = self.duck.query(sql)
        sets = [(cols, rows)]
        if self.stats_xml:
            step = STEP_BY_INDEXES[key][tuple(sorted(self.indexes))]
            sets.append((["Microsoft SQL Server 2005 XML Showplan"], [(PLANS_BY_QUERY[key][step],)]))
        return sets


INDEX_PAGES_BY_NAME = {"IX_Orders_CustomerId": 450, "IX_Orders_OrderDate_CustomerId": 610,
                       "IX_Orders_CustomerId_OrderDate": 612, "IX_Orders_Status_OrderDate": 1240,
                       "IX_Orders_Open": 14, "NCCI_Orders_Reporting": 420}


def test_sqlserver_run_end_to_end_against_a_fake_connection(db, tmp_path):
    server = FakeSqlServer(db)
    engine = labdb.SqlServerEngine(connection=server)
    lines = []
    code = lab.run_sqlserver(engine, setup=False, only=None, save_plans=tmp_path, final=True, out=lines.append)
    text = "\n".join(lines)
    assert code == 0, text
    assert "9/9 steps behaved as expected on sqlserver" in text
    assert "CREATE NONCLUSTERED INDEX [IX_Orders_CustomerId] ON [Sales].[Orders] ([CustomerId]) " \
           "INCLUDE ([OrderDate], [TotalAmount]);" in text
    assert text.count("identical to expected/ in every step") == 3
    assert len(list(tmp_path.glob("*.sqlplan"))) == 9
    # every step starts from the drop script, and the final design is what's left
    assert sum("DROP INDEX IF EXISTS IX_Orders_CustomerId " in sql for sql in server.log) == 10
    assert server.indexes == {"IX_Orders_CustomerId_OrderDate", "IX_Orders_Open", "NCCI_Orders_Reporting"}
    assert "-- dmv-index-usage.sql" in text


def test_sqlserver_run_fails_when_a_result_changes(db):
    server = FakeSqlServer(db)
    original = server.answer

    def wrong_rows(sql):
        sets = original(sql)
        if sets and sets[0][0] == ["OrderId", "OrderDate", "TotalAmount"] and "IX_Orders_CustomerId" in server.indexes:
            sets[0] = (sets[0][0], sets[0][1][:-1])     # one row missing
        return sets

    server.answer = wrong_rows
    lines = []
    code = lab.run_sqlserver(labdb.SqlServerEngine(connection=server), False, "customer-orders", None, False, lines.append)
    assert code == 1
    assert any("FAIL narrow index: rows: expected 7, got 6" in ln for ln in lines)
