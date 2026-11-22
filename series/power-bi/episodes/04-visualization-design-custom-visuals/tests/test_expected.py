"""Numbers the recorder must see: computed from the same generated data as episodes 1 and 2."""
from decimal import Decimal

import pytest

from build_star import build
from generate_export import HEADER, generate


@pytest.fixture(scope="module")
def star():
    return build([dict(zip(HEADER, [str(x) for x in r])) for r in generate(42)])


def by_category_year(star):
    cat = {p["ProductKey"]: p["Category"] for p in star["dim_product"]}
    out = {}
    for r in star["fact_sales"]:
        k = (cat[r["ProductKey"]], r["OrderDate"][:4])
        out[k] = out.get(k, Decimal(0)) + r["Quantity"] * Decimal(r["UnitPrice"])
    return out


def test_target_bullet_2025_vs_prior_year(star):
    s = by_category_year(star)
    rows = {c: (s[(c, "2025")], s[(c, "2024")]) for c in ("Accessories", "Bikes", "Clothing")}
    assert rows == {"Accessories": (Decimal("130320.98"), Decimal("120256.62")),
                    "Bikes": (Decimal("780356.80"), Decimal("716095.45")),
                    "Clothing": (Decimal("56795.10"), Decimal("58577.03"))}
    pct = {c: round((a - t) / t * 100, 1) for c, (a, t) in rows.items()}
    assert pct == {"Accessories": Decimal("8.4"), "Bikes": Decimal("9.0"), "Clothing": Decimal("-3.0")}


def test_cards_for_2025(star):
    s = by_category_year(star)
    total_2025 = sum(v for (c, y), v in s.items() if y == "2025")
    total_2024 = sum(v for (c, y), v in s.items() if y == "2024")
    assert total_2025 == Decimal("967472.88")
    assert round((total_2025 - total_2024) / total_2024 * 100, 1) == Decimal("8.1")
    orders_2025 = {r["OrderNumber"] for r in star["fact_sales"] if r["OrderDate"].startswith("2025")}
    assert len(orders_2025) == 1268


def test_showcase_units_card_and_headline_claim_for_2025(star):
    # Units card, and the Showcase headline "Sales up 8.1% in 2025 - Bikes carry the climb"
    units_2025 = sum(r["Quantity"] for r in star["fact_sales"] if r["OrderDate"].startswith("2025"))
    assert units_2025 == 3811
    s = by_category_year(star)
    growth = {c: s[(c, "2025")] - s[(c, "2024")] for c in ("Accessories", "Bikes", "Clothing")}
    total = sum(growth.values())
    assert total == Decimal("72543.78")
    assert round(growth["Bikes"] / total * 100) == 89            # Bikes carry the climb: 89% of the increase
    years = sorted({d["Year"] for d in star["dim_date"]})
    assert years == [2024, 2025, 2026]                            # the Year tiles (2026 has no sales yet)


def test_showcase_top_products_2025(star):
    prod = {p["ProductKey"]: (p["Product"], p["Category"]) for p in star["dim_product"]}
    s = {}
    for r in star["fact_sales"]:
        if r["OrderDate"].startswith("2025"):
            s[prod[r["ProductKey"]]] = s.get(prod[r["ProductKey"]], Decimal(0)) + r["Quantity"] * Decimal(r["UnitPrice"])
    top = sorted(s.items(), key=lambda kv: -kv[1])[:3]
    assert top == [(("Enduro 300", "Bikes"), Decimal("175040.40")), (("Road 300 Carbon", "Bikes"), Decimal("148440.60")),
                   (("Urban 200 E-Assist", "Bikes"), Decimal("117024.95"))]
