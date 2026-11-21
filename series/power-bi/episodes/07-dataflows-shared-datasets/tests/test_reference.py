"""The mirror of the dataflow queries: same numbers as episode 3, RLS expectations for the lab users, SharePoint layout."""
import json
from decimal import Decimal

import pytest

import pq_reference as ref
from conftest import SRC

SITE = SRC / "data" / "ContosoBikesData"
EXPECTED = json.loads((SRC / "reference" / "expected" / "summary.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary():
    return ref.summary(SITE / "exports", SITE / "security")


def test_expected_file_is_up_to_date(summary):
    assert summary == EXPECTED


def test_same_star_as_episode_3(summary):
    assert summary["files_read"] == 24
    assert summary["rows_before_dedupe"] == 4318
    assert summary["rows"] == {"Customer": 301, "Date": 1096, "Product": 19, "Sales": 4071, "Store": 5, "StoreAccess": 6}
    assert summary["sales_amount"] == "1862401.98"
    assert (summary["orders"], summary["units"]) == (2440, 7462)
    assert summary["date_range"] == ["2024-01-01", "2026-12-31"]


def test_keeping_the_older_copy_would_change_the_number(summary):
    assert summary["gotcha"]["keep_oldest_sales_amount"] == "1902513.76"
    assert summary["gotcha"]["no_dedupe_sales_amount"] == "2019894.31"


def test_rls_expectations_for_the_lab_users(summary):
    rls = summary["rls"]
    assert sorted(rls) == ["alex.demo", "riley.demo", "sam.demo", "taylor.demo"]
    assert rls["sam.demo"] == {"stores": ["Contoso Madrid"], "sales_amount": "366058.87", "orders": 484}
    assert len(rls["riley.demo"]["stores"]) == 3
    total = sum(Decimal(r["sales_amount"]) for u, r in rls.items() if u != "riley.demo")
    assert total <= Decimal(summary["sales_amount"])


def test_store_access_holds_aliases_of_lab_users_and_real_stores():
    rows = ref.store_access(SITE / "security")
    assert {r["UserAlias"] for r in rows} <= {"alex.demo", "sam.demo", "jordan.demo", "riley.demo", "taylor.demo"}
    assert all("@" not in r["UserAlias"] for r in rows)
    assert {r["StoreKey"] for r in rows} <= {1, 2, 3, 4, 5}


def test_role_members_file_uses_lab_users_only():
    lines = (SRC / "data" / "role_members.csv").read_text().splitlines()[1:]
    assert {l.split(",")[0] for l in lines} == {"alex.demo", "sam.demo", "riley.demo", "taylor.demo", "jordan.demo"}


def test_sharepoint_layout_matches_what_the_queries_filter_on():
    exports = sorted(p.name for p in (SITE / "exports").iterdir())
    assert len([n for n in exports if n.endswith(".csv")]) == 24 and "_README.txt" in exports
    assert [p.name for p in (SITE / "security").iterdir()] == ["store_access.csv"]
    sales = (SRC / "dataflow" / "queries" / "SalesExport.pq").read_text()
    assert 'Text.EndsWith([Folder Path], "/exports/")' in sales and 'Text.Lower([Extension]) = ".csv"' in sales
    assert 'Text.EndsWith([Folder Path], "/security/")' in (SRC / "dataflow" / "queries" / "StoreAccess.pq").read_text()


def test_nothing_real_in_the_site_url_or_the_data():
    url = (SRC / "dataflow" / "queries" / "ExportSite.pq").read_text()
    assert "https://contoso.sharepoint.com/sites/ContosoBikesData" in url
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix in {".pq", ".tmdl", ".json", ".csv", ".ps1", ".psm1", ".py"} and not {"node_modules", "dist", "bin", "obj"} & set(p.parts):
            assert "devladlog" not in p.read_text(encoding="utf-8", errors="ignore").lower().replace("devladlog.com", ""), p
