import csv
import json
import subprocess
import sys

import pytest

import expected
import make_contract
import verify_pdf
from conftest import SRC, render_fake_pdf


def test_contract_file_is_up_to_date():
    assert (SRC / "contract" / "store-statement-2025.json").read_text(encoding="utf-8") == make_contract.render()


def test_contract_matches_an_independent_sum_of_the_csv():
    total = sum(float(m["sales_amount"].replace(",", "")) for s in make_contract.build()["stores"] for m in s["months"])
    direct = 0.0
    for r in csv.DictReader((SRC / "data" / "star" / "fact_sales.csv").open(encoding="utf-8")):
        if r["OrderDate"].startswith("2025-"):
            direct += int(r["Quantity"]) * float(r["UnitPrice"])
    assert total == pytest.approx(direct, abs=0.6)       # 60 rows rounded to cents


def test_contract_shape(contract):
    assert contract["pages"] == len(contract["stores"]) == 5
    assert all(len(s["months"]) == 12 for s in contract["stores"])
    assert [s["store"] for s in contract["stores"]] == sorted(s["store"] for s in contract["stores"])


def test_both_years_of_the_star_have_rows():
    for year in (2024, 2025):
        rows = expected.statement_rows(year)
        assert rows, year


def test_good_simulated_pdf_passes(tmp_path, contract):
    pdf = tmp_path / "ok.pdf"
    render_fake_pdf(contract, pdf)
    assert verify_pdf.verify(pdf, contract) == []


def test_changed_figure_is_reported(tmp_path, contract):
    pdf = tmp_path / "bad.pdf"
    render_fake_pdf(contract, pdf, tamper=("Contoso Paris", "Mar"))
    problems = verify_pdf.verify(pdf, contract)
    assert len(problems) == 1 and "Contoso Paris" in problems[0] and "Mar" in problems[0]


def test_blank_pages_are_reported(tmp_path, contract):
    pdf = tmp_path / "blank.pdf"
    render_fake_pdf(contract, pdf, blank_after_each=True)
    problems = verify_pdf.verify(pdf, contract)
    assert any("10 pages, expected 5" in p for p in problems)


def test_cli_exit_codes(tmp_path, contract):
    good, bad = tmp_path / "g.pdf", tmp_path / "b.pdf"
    render_fake_pdf(contract, good)
    render_fake_pdf(contract, bad, tamper=("Contoso Lisboa", "Jan"))
    run = lambda f: subprocess.run([sys.executable, str(SRC / "tools" / "verify_pdf.py"), str(f)], capture_output=True, text=True)
    assert run(good).returncode == 0 and run(bad).returncode == 1
