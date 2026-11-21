#!/usr/bin/env python3
"""What every user should see under the episode's RLS roles, computed in plain Python from the same generated data.

Why: RLS filters are DAX and only run inside the Analysis Services engine (Power BI Desktop on Windows or the
service). This module applies the same rules by hand, following the documented semantics:

  * Store Managers: Store rows whose StoreKey is mapped to the user's UPN in store_access.csv; a UPN that isn't
    mapped gets no Store rows (CALCULATETABLE over an empty table returns an empty set)
  * Head Office: no filters, every row
  * roles are additive: a user in several roles sees the union (Learn: RLS guidance)
  * a user in no role sees nothing
  * filters propagate from the one side to the many side of active relationships (Store -> Sales); Sales -> Customer
    also passes the filter on because that relationship applies security filters in both directions

Usage:
    python rls_reference.py           # writes expected/rls_matrix.csv and prints it
"""
import csv
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(DATA))

from build_star import build                      # noqa: E402
from generate_export import HEADER, generate      # noqa: E402

COLUMNS = ["UserAlias", "Roles", "Visible Stores", "Visible Customers", "Visible Customers One Way",
           "Sales Amount", "Orders", "Stores", "Service"]


def read_csv(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_star():
    return build([dict(zip(HEADER, [str(x) for x in r])) for r in generate(42)])


def store_access():
    """{alias: {StoreKey}} from the security mapping table."""
    out = {}
    for r in read_csv("store_access.csv"):
        out.setdefault(r["UserAlias"].strip().lower(), set()).add(int(r["StoreKey"]))
    return out


def role_members():
    out = {}
    for r in read_csv("role_members.csv"):
        out.setdefault(r["UserAlias"].strip().lower(), set()).add(r["Role"])
    return out


def visible_store_keys(star, alias, roles, access):
    """Union of the role filters on Store."""
    all_keys = {s["StoreKey"] for s in star["dim_store"]}
    keys = set()
    for role in roles:
        if role == "Head Office":
            keys |= all_keys
        elif role == "Store Managers":
            keys |= access.get(alias, set()) & all_keys
        else:
            raise ValueError(f"unknown role {role}")
    return keys


def evaluate(star, alias, roles, access, service=True):
    alias = alias.lower()
    stores = visible_store_keys(star, alias, roles, access)
    unfiltered = "Head Office" in roles
    lines = [r for r in star["fact_sales"] if r["StoreKey"] in stores]
    if unfiltered:
        customers = len(star["dim_customer"])
    else:
        customers = len({r["CustomerKey"] for r in lines})        # security filter both directions on Sales -> Customer
    one_way = len(star["dim_customer"]) if roles else 0           # same role without it: Customer isn't filtered
    names = {s["StoreKey"]: s["Store"] for s in star["dim_store"]}
    return {
        "UserAlias": alias,
        "Roles": "+".join(sorted(roles)) or "(none)",
        "Visible Stores": len(stores),
        "Visible Customers": customers if roles else 0,
        "Visible Customers One Way": one_way,
        "Sales Amount": sum((r["Quantity"] * Decimal(r["UnitPrice"]) for r in lines), Decimal("0.00")),
        "Orders": len({r["OrderNumber"] for r in lines}),
        "Stores": "; ".join(names[k] for k in sorted(stores)),
        "Service": "yes" if service else "no",     # no = only testable in Desktop (View as > Other user)
    }


def matrix(star=None):
    star = star or load_star()
    access, members = store_access(), role_members()
    rows = [evaluate(star, alias, roles, access) for alias, roles in members.items()]
    # Desktop-only checks (View as > Other user): a UPN that isn't in the mapping table, and nobody's role at all.
    rows.append(evaluate(star, "nobody.demo", {"Store Managers"}, access, service=False))
    rows.append(evaluate(star, "no.role.demo", set(), access, service=False))
    return rows


def write(rows, path=HERE / "expected" / "rls_matrix.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "Sales Amount": f"{r['Sales Amount']:.2f}"})
    return path


if __name__ == "__main__":
    rows = matrix()
    print(write(rows).read_text(encoding="utf-8"), end="")
