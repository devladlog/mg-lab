"""The expected RLS matrix: computed from the same generated data as episodes 1-4 and committed for the recorder."""
import csv
import sys
from decimal import Decimal

import pytest

from conftest import SRC

sys.path.insert(0, str(SRC / "reference"))
import rls_reference as ref  # noqa: E402

LAB_USERS = {"alex.demo", "sam.demo", "jordan.demo", "riley.demo", "taylor.demo"}   # series/LAB.md


@pytest.fixture(scope="module")
def star():
    return ref.load_star()


@pytest.fixture(scope="module")
def rows(star):
    return {r["UserAlias"]: r for r in ref.matrix(star)}


def test_committed_matrix_is_up_to_date(star, tmp_path):
    fresh = ref.write(ref.matrix(star), tmp_path / "rls_matrix.csv")
    assert fresh.read_text() == (SRC / "reference" / "expected" / "rls_matrix.csv").read_text()


def test_mapping_only_uses_lab_users_and_existing_stores(star):
    stores = {s["StoreKey"] for s in star["dim_store"]}
    with open(SRC / "data" / "store_access.csv", newline="") as f:
        mapping = list(csv.DictReader(f))
    assert {r["UserAlias"] for r in mapping} <= LAB_USERS
    assert {int(r["StoreKey"]) for r in mapping} <= stores
    assert len({(r["UserAlias"], r["StoreKey"]) for r in mapping}) == len(mapping)      # no duplicate rows


def test_role_members_are_lab_users_in_known_roles():
    with open(SRC / "data" / "role_members.csv", newline="") as f:
        members = list(csv.DictReader(f))
    assert {m["UserAlias"] for m in members} <= LAB_USERS
    assert {m["Role"] for m in members} == {"Store Managers", "Head Office"}
    roles = {p.stem for p in (SRC / "ContosoSales.SemanticModel" / "definition" / "roles").glob("*.tmdl")}
    assert {m["Role"] for m in members} == roles


def test_store_managers_see_their_stores(rows):
    assert rows["alex.demo"]["Stores"] == "Contoso Lisboa"
    assert rows["sam.demo"]["Stores"] == "Contoso Madrid"
    assert rows["taylor.demo"]["Stores"] == "Contoso Paris"
    assert rows["riley.demo"]["Stores"] == "Contoso Lisboa; Contoso Online; Contoso Porto"
    assert rows["alex.demo"]["Sales Amount"] == Decimal("389707.34")
    assert rows["sam.demo"]["Sales Amount"] == Decimal("366058.87")


def test_head_office_sees_the_episode_1_totals(rows):
    jordan = rows["jordan.demo"]
    assert (jordan["Visible Stores"], jordan["Visible Customers"], jordan["Orders"]) == (5, 301, 2440)
    assert jordan["Sales Amount"] == Decimal("1862401.98")


def test_store_rows_add_up_to_the_total(star):
    access = {f"store{k}": {k} for k in range(1, 6)}
    parts = [ref.evaluate(star, a, {"Store Managers"}, access)["Sales Amount"] for a in access]
    assert sum(parts) == Decimal("1862401.98")


def test_a_country_manager_sees_the_union_of_three_stores(star, rows):
    access = ref.store_access()
    single = [ref.evaluate(star, "x", {"Store Managers"}, {"x": {k}})["Sales Amount"] for k in access["riley.demo"]]
    assert rows["riley.demo"]["Sales Amount"] == sum(single) == Decimal("1111159.04")


def test_roles_are_additive(star):
    both = ref.evaluate(star, "alex.demo", {"Store Managers", "Head Office"}, ref.store_access())
    assert both["Visible Stores"] == 5


def test_an_unmapped_upn_sees_nothing(rows):
    nobody = rows["nobody.demo"]
    assert (nobody["Visible Stores"], nobody["Visible Customers"], nobody["Orders"]) == (0, 0, 0)
    assert nobody["Service"] == "no"


def test_customer_list_is_filtered_only_with_security_both_directions(rows):
    for alias in ("alex.demo", "sam.demo", "taylor.demo", "riley.demo"):
        assert rows[alias]["Visible Customers"] < rows[alias]["Visible Customers One Way"] == 301
    assert rows["alex.demo"]["Visible Customers"] == 247
