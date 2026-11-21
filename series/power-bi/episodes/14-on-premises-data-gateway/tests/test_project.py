"""Checks that need no tenant, no gateway and no SQL Server (pytest, standard library + sqlglot for the T-SQL syntax check)."""
import csv
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

EP = Path(__file__).resolve().parent.parent
SRC = EP / "src"
sys.path.insert(0, str(SRC / "tools"))
import expected  # noqa: E402

ZERO_GUID = re.compile(r"^0{8}-0{4}-0{4}-0{4}-[0-9a-f]{12}$")
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def test_query_and_datasource_definition_agree():
    """The link between a model and a gateway data source is server + database, exactly (Learn: 'Manage a SQL Server data source')."""
    ds = json.loads((SRC / "gateway" / "datasource.json").read_text(encoding="utf-8"))
    m = (SRC / "queries" / "sales-by-store.pq").read_text(encoding="utf-8")
    found = re.findall(r'Sql\.Database\(\s*"([^"]*)"\s*,\s*"([^"]*)"', m)
    assert found == [(ds["server"], ds["database"])]
    assert ds["type"] == "Sql" and ds["authentication"] == "Basic"


def test_no_secret_in_the_datasource_definition_or_scripts():
    ds = json.loads((SRC / "gateway" / "datasource.json").read_text(encoding="utf-8"))
    assert not {"password", "secret", "key"} & {k.lower() for k in ds}
    for f in list(SRC.rglob("*.ps1")) + list(SRC.rglob("*.psm1")) + list(SRC.rglob("*.cs")) + list(SRC.rglob("*.sql")):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"PASSWORD\s*=\s*N'(?!\$\()", text, re.I), f"literal password in {f.name}"
        assert "devladlog" not in text.lower(), f.name


def test_only_zero_guids_in_the_repo_files():
    files = [f for f in EP.rglob("*") if f.is_file() and f.suffix in {".json", ".ps1", ".psm1", ".psd1", ".md", ".yaml", ".sql", ".cs", ".pq"}]
    assert files
    for f in files:
        for g in GUID.findall(f.read_text(encoding="utf-8")):
            assert ZERO_GUID.match(g.lower()), f"{f.relative_to(EP)}: {g} is not a zero GUID"


def _batches(sql: str):
    return [b.strip() for b in re.split(r"^\s*GO\s*$", sql, flags=re.M | re.I) if b.strip()]


@pytest.mark.parametrize("name", ["01-gateway-login.sql", "02-checks.sql", "99-teardown.sql"])
def test_tsql_parses(name):
    sqlglot = pytest.importorskip("sqlglot")
    text = (SRC / "sql" / name).read_text(encoding="utf-8").replace("$(GatewayPassword)", "x")
    n = 0
    for batch in _batches(text):
        for stmt in sqlglot.parse(batch, read="tsql"):
            assert stmt is not None
            n += 1
    assert n >= 3


def test_login_is_read_only_and_teardown_removes_what_was_created():
    login = (SRC / "sql" / "01-gateway-login.sql").read_text(encoding="utf-8")
    assert "db_datareader" in login and "db_datawriter" not in login and "db_owner" not in login
    assert "sysadmin" not in login.lower().replace("-- ", "").replace("as a sysadmin", "")
    tear = (SRC / "sql" / "99-teardown.sql").read_text(encoding="utf-8")
    assert "DROP USER [pbi_gateway_reader]" in tear and "DROP LOGIN [pbi_gateway_reader]" in tear


def test_expected_numbers():
    t = expected.totals()
    assert t["lines"] == 4071 and t["stores"] == 5
    assert t["amount"] == Decimal("1862401.98")
    amount, _ = expected.load()
    assert amount["Contoso Lisboa"] == Decimal("389707.34")      # episode 5: Alex
    assert amount["Contoso Madrid"] == Decimal("366058.87")      # episode 5: Sam
    assert amount["Contoso Paris"] == Decimal("385184.07")       # episode 5: Taylor
    assert amount["Contoso Lisboa"] + amount["Contoso Online"] + amount["Contoso Porto"] == Decimal("1111159.04")  # episode 5: Riley
    assert sum(amount.values()) == t["amount"]


def test_data_is_the_same_as_episode_11_when_it_is_next_to_this_one():
    other = EP.parent / "11-composite-models-directquery" / "src" / "data" / "star"
    if not other.is_dir():
        pytest.skip("episode 11 folder not present")
    for name in ("fact_sales.csv", "dim_store.csv"):
        a = hashlib.sha256((SRC / "data" / "star" / name).read_bytes()).hexdigest()
        b = hashlib.sha256((other / name).read_bytes()).hexdigest()
        assert a == b, name


def test_sql_scripts_use_the_tables_the_query_reads():
    q = (SRC / "queries" / "sales-by-store.pq").read_text(encoding="utf-8")
    checks = (SRC / "sql" / "02-checks.sql").read_text(encoding="utf-8")
    for table in ("FactSales", "DimStore"):
        assert table in q and f"dbo.{table}" in checks
    # the columns the query uses exist in the CSV headers of the star
    fact = next(csv.reader((SRC / "data" / "star" / "fact_sales.csv").open(encoding="utf-8")))
    assert {"StoreKey", "OrderNumber"} <= set(fact)


def test_module_manifest_exports_what_the_module_exports():
    psd = (SRC / "ps" / "GatewayOps" / "GatewayOps.psd1").read_text(encoding="utf-8")
    psm = (SRC / "ps" / "GatewayOps" / "GatewayOps.psm1").read_text(encoding="utf-8")
    manifest = set(re.findall(r"'([A-Z][A-Za-z]+-[A-Za-z]+)'", re.search(r"FunctionsToExport = @\((.*?)\)", psd, re.S).group(1)))
    exported = set(re.findall(r"[A-Z][a-z]+-[A-Za-z]+", psm[psm.index("Export-ModuleMember") + len("Export-ModuleMember"):]))
    assert manifest == exported
    assert len(manifest) == 13
