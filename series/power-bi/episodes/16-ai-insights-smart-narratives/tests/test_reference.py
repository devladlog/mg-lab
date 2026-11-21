"""reference_insights: the directional numbers the demo compares the AI visuals against."""
import re

import ai_readiness as ar
import reference_insights as ri

EXPLAIN = ["Channel", "Store Country", "Customer Country", "Contains Bike", "Lines", "Delivery"]


def test_planted_drivers_come_out_on_top(star):
    rows = ar.read_csv(star / "order_profile.csv")
    top = ri.influencers(rows, "Survey Rating", "Low", EXPLAIN)
    assert [(x["field"], x["value"]) for x in top[:2]] == [("Delivery", "Slow"), ("Channel", "Online")]
    assert 2.8 <= top[0]["lift"] <= 4.0 and 1.4 <= top[1]["lift"] <= 2.0
    # the features that carry no planted effect stay close to 1
    bike = next(x for x in top if (x["field"], x["value"]) == ("Contains Bike", "Yes"))
    assert bike["lift"] < 1.3


def test_lift_is_the_ratio_the_learn_page_describes():
    rows = [{"SurveyRating": "Low" if i < 20 else "High", "Channel": "A" if i < 50 else "B"} for i in range(100)]
    x = next(v for v in ri.influencers(rows, "Survey Rating", "Low", ["Channel"], min_n=10) if v["value"] == "A")
    assert (x["rate_in"], x["rate_out"], x["lift"]) == (0.4, 0.0, float("inf"))
    rows[60]["SurveyRating"] = "Low"   # one Low among the 50 in B
    x = next(v for v in ri.influencers(rows, "Survey Rating", "Low", ["Channel"], min_n=10) if v["value"] == "A")
    assert round(x["rate_out"], 2) == 0.02 and round(x["lift"]) == 20


def test_without_a_planted_effect_nothing_stands_out(star):
    """Order Size is a function of the basket, not a survey: Contains Bike separates it perfectly (the lift is infinite)."""
    rows = ar.read_csv(star / "order_profile.csv")
    top = ri.influencers(rows, "Order Size", "Large", EXPLAIN)
    assert (top[0]["field"], top[0]["value"], top[0]["lift"]) == ("Contains Bike", "Yes", float("inf"))


def test_anomalies_flags_a_planted_spike_and_ignores_a_flat_series():
    pts = [(f"2025-01-{d:02d}", 100.0 + (d % 3)) for d in range(1, 29)]
    assert ri.anomalies(pts) == []
    pts[14] = (pts[14][0], 900.0)
    found = ri.anomalies(pts)
    assert found[0][0] == "2025-01-15" and found[0][2] > 4


def test_anomalies_on_the_real_series_are_few_and_dated(star):
    found = ri.anomalies(ar.daily_sales(star))
    assert 1 <= len(found) <= 20
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\d", d) for d, _, _ in found)


def test_narrative_expected_text(star):
    n = ri.narrative(star, 2025)
    assert re.fullmatch(r"Sales were [\d,]+ in the selected period\.", n["Narrative Sales"])
    assert n["Narrative Sales"] == "Sales were 967,473 in the selected period."
    assert n["Narrative YoY"] == "That is 8.1% above the same period last year."
    assert n["Narrative Top Category"] == "Bikes leads the mix."
    first = ri.narrative(star, 2024)   # 2023 has no data
    assert first["Narrative YoY"] == "There is no prior-year period to compare with."


def test_cli_prints_the_three_sections(star, capsys):
    assert ri.main(["--star", str(star)]) == 0
    out = capsys.readouterr().out
    assert "Delivery is Slow" in out and "Candidate anomaly days" in out and "Narrative Top Category" in out
