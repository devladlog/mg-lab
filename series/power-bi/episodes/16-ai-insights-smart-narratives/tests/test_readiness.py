"""ai_readiness: every rule fires on a small broken input, and stays quiet on the real order profile."""
import subprocess
import sys
from pathlib import Path

import ai_readiness as ar
from conftest import MODEL, SRC


def rows(n_low, n_high, extra=None):
    out = [{"SurveyRating": "Low", "Channel": "Store", "Delivery": "Fast"} for _ in range(n_low)]
    out += [{"SurveyRating": "High", "Channel": "Store", "Delivery": "Fast"} for _ in range(n_high)]
    return out + (extra or [])


def rules(findings):
    return sorted(f["rule"] for f in findings)


def test_real_profile_is_clean(star):
    r = ar.read_csv(star / "order_profile.csv")
    assert ar.check_key_influencers(r, "Survey Rating", "Low", ["Channel", "Delivery", "Contains Bike"], MODEL) == []
    assert ar.check_anomaly_series(ar.daily_sales(star)) == []


def test_too_few_observations_of_the_selected_state():
    assert rules(ar.check_key_influencers(rows(99, 500), "Survey Rating", "Low", ["Channel"])) == ["AI001"]
    assert rules(ar.check_key_influencers(rows(100, 500), "Survey Rating", "Low", ["Channel"])) == []


def test_too_few_observations_to_compare_with():
    assert rules(ar.check_key_influencers(rows(150, 9), "Survey Rating", "Low", ["Channel"])) == ["AI002"]
    assert rules(ar.check_key_influencers(rows(150, 10), "Survey Rating", "Low", ["Channel"])) == []


def test_outcome_with_many_unique_values():
    r = [{"SurveyRating": f"v{i % 11}", "Channel": "Store"} for i in range(2200)]
    assert "AI003" in rules(ar.check_key_influencers(r, "Survey Rating", "v0", ["Channel"]))


def test_thin_explain_by_category():
    extra = [{"SurveyRating": "High", "Channel": "Kiosk", "Delivery": "Fast"} for _ in range(3)]
    found = ar.check_key_influencers(rows(150, 500, extra), "Survey Rating", "Low", ["Channel"])
    assert rules(found) == ["AI004"] and "Kiosk" in found[0]["message"]


def test_outcome_in_explain_by():
    assert rules(ar.check_key_influencers(rows(150, 500), "Survey Rating", "Low", ["Survey Rating"])) == ["AI006"]


def test_sample_cap_is_information_not_an_error():
    found = ar.check_key_influencers(rows(150, 10_000), "Survey Rating", "Low", ["Channel"])
    assert [(f["rule"], f["severity"]) for f in found] == [("AI005", "info")]


def test_discourage_implicit_measures_is_detected(tmp_path):
    (tmp_path / "model.tmdl").write_text("model Model\n\tculture: en-US\n\tdiscourageImplicitMeasures\n", encoding="utf-8")
    assert ar.discourages_implicit_measures(tmp_path)
    (tmp_path / "model.tmdl").write_text("model Model\n\tdiscourageImplicitMeasures: true\n", encoding="utf-8")
    assert ar.discourages_implicit_measures(tmp_path)
    (tmp_path / "model.tmdl").write_text("model Model\n\tculture: en-US\n\tdiscourageImplicitMeasures: false\n", encoding="utf-8")
    assert not ar.discourages_implicit_measures(tmp_path)
    assert not ar.discourages_implicit_measures(MODEL)


def test_episode_4_model_conflicts_with_key_influencers(star):
    ep4 = Path(__file__).resolve().parents[2] / "04-visualization-design-custom-visuals/src/ContosoSales.SemanticModel/definition"
    if not ep4.exists():
        return  # the episode folder is shipped on its own
    r = ar.read_csv(star / "order_profile.csv")
    assert "AI007" in rules(ar.check_key_influencers(r, "Survey Rating", "Low", ["Channel"], ep4))


def test_anomaly_series_rules():
    assert rules(ar.check_anomaly_series([("2025-01-01", 1), ("2025-01-02", 2), ("2025-01-03", 3)])) == ["AI008"]
    assert rules(ar.check_anomaly_series([("2025-01-01", 1)] * 4)) == ["AI009"]
    assert ar.check_anomaly_series([(f"2025-01-0{i}", i) for i in range(1, 5)]) == []


def test_cli_exit_codes(star):
    cmd = [sys.executable, str(SRC / "ai_readiness.py"), "--star", str(star), "--model", str(MODEL)]
    ok = subprocess.run(cmd, capture_output=True, text=True)
    assert ok.returncode == 0 and "no findings" in ok.stdout
    bad = subprocess.run(cmd + ["--target", "Nope"], capture_output=True, text=True)
    assert bad.returncode == 1 and "AI001" in bad.stdout
