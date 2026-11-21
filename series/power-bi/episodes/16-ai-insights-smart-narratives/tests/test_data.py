"""The order profile: one row per order, derived from the star schema, with a labelled simulated rating."""
import csv
from collections import Counter

import build_order_profile as bop
from ai_readiness import read_csv


def test_one_row_per_order(star):
    fact = read_csv(star / "fact_sales.csv")
    profile = read_csv(star / "order_profile.csv")
    assert len(profile) == len({r["OrderNumber"] for r in fact}) == 2440
    assert len({r["OrderNumber"] for r in profile}) == len(profile)
    assert list(profile[0]) == bop.FIELDS


def test_order_value_and_units_match_the_fact_lines(star):
    fact = read_csv(star / "fact_sales.csv")
    profile = {r["OrderNumber"]: r for r in read_csv(star / "order_profile.csv")}
    assert round(sum(float(r["OrderValue"]) for r in profile.values()), 2) == round(
        sum(int(r["Quantity"]) * float(r["UnitPrice"]) for r in fact), 2)
    assert sum(int(r["Units"]) for r in profile.values()) == sum(int(r["Quantity"]) for r in fact)
    assert sum(int(r["Lines"]) for r in profile.values()) == len(fact)


def test_size_and_delivery_rules():
    assert [bop.order_size(v) for v in (99.99, 100, 999.99, 1000)] == ["Small", "Medium", "Medium", "Large"]


def test_derived_columns_follow_their_rules(star):
    for r in read_csv(star / "order_profile.csv"):
        assert r["OrderSize"] == bop.order_size(float(r["OrderValue"]))
        assert (r["Delivery"] == "Slow") == (int(r["ShipDays"]) > bop.SLOW_ABOVE_DAYS)
        assert r["SurveyRating"] in {"High", "Low"}
        assert r["CustomerCountry"] != ""


def test_the_profile_is_deterministic(star, tmp_path):
    again = bop.build_profile(star)
    assert again == bop.build_profile(star)
    assert bop.build_profile(star, seed=7) != again  # the simulated rating depends on the seed


def test_planted_rating_effect_is_in_the_data(star):
    rows = read_csv(star / "order_profile.csv")
    def low(cond):
        sel = [r for r in rows if cond(r)]
        return sum(r["SurveyRating"] == "Low" for r in sel) / len(sel)
    assert low(lambda r: r["Delivery"] == "Slow") > 2.5 * low(lambda r: r["Delivery"] == "Fast")
    assert low(lambda r: r["Channel"] == "Online") > 1.3 * low(lambda r: r["Channel"] == "Store")
    assert Counter(r["SurveyRating"] for r in rows)["Low"] >= 100  # the visual's minimum for the selected state
