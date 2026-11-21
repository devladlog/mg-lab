"""The two lab workbooks are real .xlsx files with Excel tables (the connector only works with tables)."""
import pytest

from excelfake import scenario
from excelfake.workbook import ExcelDate, Workbook

openpyxl = pytest.importorskip("openpyxl")


def test_price_list_round_trips_through_xlsx(tmp_path):
    path = scenario.price_list().save_xlsx(tmp_path / scenario.PRICE_FILE)
    xwb = openpyxl.load_workbook(path)
    assert list(xwb["Prices"].tables) == ["Prices"]
    wb = Workbook.load_xlsx(path)
    t = wb.tables["Prices"]
    assert t.headers == ["Item No.", "Description", "Unit price", "Valid from"]
    assert len(t.rows) == 400 and t.rows[0][3] == ExcelDate(46357.0)
    assert t.rows[-2][2] == "12,50"           # the price typed as text stays text


def test_catalogue_round_trips_through_xlsx(tmp_path):
    path = scenario.catalogue().save_xlsx(tmp_path / scenario.CATALOGUE_FILE)
    t = Workbook.load_xlsx(path).tables["Catalogue"]
    assert len(t.rows) == 381 and [r[0] for r in t.rows].count("FAB-0007") == 2
    assert path.stat().st_size < 100_000
