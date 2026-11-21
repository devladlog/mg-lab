"""In-memory Excel workbooks with tables, and real .xlsx files for the lab (openpyxl).

Excel stores dates as serial numbers: days since 30 December 1899 (Learn, "Work with dates using the
Excel JavaScript API": 1 January 2000 is 36526). A cell here is a str, int, float, bool, None or an
ExcelDate (a serial number that Excel displays as a date).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class ExcelDate:
    serial: float

    @classmethod
    def of(cls, d: date) -> "ExcelDate":
        return cls(float((d - EPOCH).days))

    def to_date(self) -> date:
        return EPOCH + timedelta(days=int(self.serial))


def to_serial(d: date) -> int:
    return (d - EPOCH).days


@dataclass
class Table:
    name: str
    headers: list[str]
    rows: list[list] = field(default_factory=list)

    def column(self, name: str) -> int:
        return self.headers.index(name)


@dataclass
class Workbook:
    name: str
    tables: dict[str, Table] = field(default_factory=dict)

    def add_table(self, name: str, headers: list[str], rows=None) -> Table:
        t = Table(name, list(headers), [list(r) for r in (rows or [])])
        self.tables[name] = t
        return t

    def copy(self) -> "Workbook":
        return copy.deepcopy(self)

    # ------------------------------------------------------------------ xlsx
    def save_xlsx(self, path: str | Path, date_columns: dict[str, set[str]] | None = None) -> Path:
        """Write a real workbook: one worksheet per table, formatted as an Excel table."""
        from openpyxl import Workbook as XWorkbook
        from openpyxl.worksheet.table import Table as XTable, TableStyleInfo
        from openpyxl.utils import get_column_letter

        wb = XWorkbook()
        wb.remove(wb.active)
        for t in self.tables.values():
            ws = wb.create_sheet(t.name)
            ws.append(t.headers)
            for row in t.rows:
                ws.append([c.to_date() if isinstance(c, ExcelDate) else c for c in row])
            for ci, h in enumerate(t.headers, start=1):
                ws.column_dimensions[get_column_letter(ci)].width = max(12, len(h) + 4)
                if any(isinstance(r[ci - 1], ExcelDate) for r in t.rows):
                    for r in range(2, len(t.rows) + 2):
                        ws.cell(row=r, column=ci).number_format = "yyyy-mm-dd"
            last = f"{get_column_letter(len(t.headers))}{max(len(t.rows), 1) + 1}"
            xt = XTable(displayName=t.name, ref=f"A1:{last}")
            xt.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            ws.add_table(xt)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
        return path

    @classmethod
    def load_xlsx(cls, path: str | Path) -> "Workbook":
        """Read every Excel table (not plain ranges: the connector only works with tables)."""
        from openpyxl import load_workbook

        xwb = load_workbook(path)
        wb = cls(Path(path).name)
        for ws in xwb.worksheets:
            for name, ref in ws.tables.items():
                cells = ws[ref]
                headers = [str(c.value) for c in cells[0]]
                rows = []
                for line in cells[1:]:
                    row = []
                    for c in line:
                        v = c.value
                        if isinstance(v, datetime):
                            v = ExcelDate.of(v.date())
                        elif isinstance(v, date):
                            v = ExcelDate.of(v)
                        row.append(v)
                    if any(v is not None for v in row):
                        rows.append(row)
                wb.add_table(name, headers, rows)
        return wb
