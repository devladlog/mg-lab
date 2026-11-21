import csv
import json
import subprocess
import sys
from decimal import Decimal

import pytest

from conftest import CATEGORY_MODEL, DATA, EPISODE, STAR
from copilot_pbi import cost, golden
from copilot_pbi.cli import main


# ---- cost: the worked examples printed on Microsoft Learn ----

def test_learn_example_one_request_is_400_cu_seconds():
    # Learn: 2,000 input and 500 output tokens = (2000*100 + 500*400)/1000 = 400 CU seconds = 6.67 CU minutes
    assert cost.cu_seconds_per_prompt(2000, 500) == 400.0
    assert round(400 / 60, 2) == 6.67


def test_learn_example_f64_runs_13824_requests_a_day():
    e = cost.estimate("F64", 1, 2000, 500)
    assert round(e.prompts_per_day_to_exhaust) == 13824


def test_cached_tokens_cost_a_tenth():
    assert cost.cu_seconds_per_prompt(1000, 0, cached_share=1.0) == 10.0
    assert cost.cu_seconds_per_prompt(1000, 0, cached_share=0.5) == 55.0
    with pytest.raises(ValueError):
        cost.cu_seconds_per_prompt(1, 1, cached_share=1.5)


def test_sku_table_and_price():
    assert cost.SKU_CU["F2"] == 2 and cost.SKU_CU["P1"] == cost.SKU_CU["F64"] == 64
    e = cost.estimate("f2", 100, 8000, 600, price_per_cu_hour=0.1975, window_hours=3)
    assert e.cu == 2 and round(e.capacity_cost_per_hour, 3) == 0.395 and round(e.window_cost, 3) == 1.185
    with pytest.raises(ValueError):
        cost.estimate("F3", 1, 1, 1)


def test_f2_is_small_for_a_busy_day():
    e = cost.estimate("F2", 200, 8000, 600)
    assert e.cu_seconds_per_prompt == 1040.0
    assert e.share_of_daily_capacity > 1.0    # 200 such prompts exceed one day of F2: the lab must keep prompts few


# ---- golden answers computed from the CSV files ----

needs_star = pytest.mark.skipif(not STAR.exists(), reason="Power BI episode 1 data not in this checkout")


def _rows(name):
    with (STAR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@needs_star
def test_golden_total_matches_an_independent_sum():
    total = sum(Decimal(r["Quantity"]) * Decimal(r["UnitPrice"]) for r in _rows("fact_sales.csv") if r["OrderDate"][:4] == "2025")
    g = {r["id"]: r for r in golden.compute(STAR)}
    assert g["G1"]["raw"] == total
    assert g["G1"]["expected"] == f"{total:,.2f}"


@needs_star
def test_golden_ship_date_differs_from_order_date():
    g = {r["id"]: r for r in golden.compute(STAR, 2025, 6)}
    fact = _rows("fact_sales.csv")
    ordered = len({r["OrderNumber"] for r in fact if r["OrderDate"].startswith("2025-06")})
    shipped = len({r["OrderNumber"] for r in fact if r["ShipDate"].startswith("2025-06")})
    assert (ordered, shipped) == (145, 149) and g["G4"]["raw"] == 149 and str(ordered) in g["G4"]["expected"]


@needs_star
def test_golden_country_question_is_really_ambiguous():
    g = {r["id"]: r for r in golden.compute(STAR)}
    exp = g["G5"]["expected"]
    cust, store = exp.split(" | ")
    assert cust != store and "Unknown" in cust and "Unknown" not in store


@needs_star
def test_golden_top3_stores_and_best_category_are_sorted_correctly():
    g = {r["id"]: r for r in golden.compute(STAR)}
    assert g["G2"]["expected"].startswith("Bikes ")
    vals = g["G3"]["raw"]
    assert len(vals) == 3 and vals == sorted(vals, reverse=True)


# ---- CLI ----

def test_cli_cost_prints_the_numbers(capsys):
    assert main(["cost", "--sku", "F2", "--prompts-per-day", "10", "--price-per-cu-hour", "0.1975", "--window-hours", "3"]) == 0
    out = capsys.readouterr().out
    assert "one prompt: 1,040.0 CU seconds" in out and "0.395 EUR/hour" in out and "recording window 3 h: 1.19 EUR" in out


@pytest.mark.skipif(not CATEGORY_MODEL.exists(), reason="Power BI episode 1 model not in this checkout")
def test_cli_lint_exit_codes_and_json(capsys, tmp_path):
    assert main(["lint", str(CATEGORY_MODEL)]) == 0                       # warnings only
    assert main(["lint", str(CATEGORY_MODEL), "--fail-on", "warning"]) == 1
    capsys.readouterr()
    assert main(["lint", str(CATEGORY_MODEL), "--instructions", str(DATA / "ai-instructions-contoso-bikes.md")]) == 1  # [Orders Shipped] missing
    capsys.readouterr()
    assert main(["lint", str(CATEGORY_MODEL), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["summary"] == {"error": 0, "warning": 7, "info": 0}
    out = tmp_path / "m"
    assert main(["describe", str(CATEGORY_MODEL), str(DATA / "descriptions-contoso-bikes.json"), "--out", str(out)]) == 0
    assert main(["lint", str(out), "--instructions", str(DATA / "ai-instructions-contoso-bikes.md"),
                 "--verified", str(DATA / "verified-answers-plan.json"), "--fail-on", "info"]) == 0


def test_cli_reports_a_missing_folder(capsys, tmp_path):
    assert main(["lint", str(tmp_path / "nope")]) == 2
    assert "error:" in capsys.readouterr().err


def test_module_entry_point_runs():
    r = subprocess.run([sys.executable, "-m", "copilot_pbi", "cost", "--sku", "F64"], cwd=EPISODE / "src",
                       capture_output=True, text=True)
    assert r.returncode == 0 and "SKU F64: 64 CU" in r.stdout
