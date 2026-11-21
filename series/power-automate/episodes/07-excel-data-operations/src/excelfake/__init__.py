"""excelfake: the Excel Online (Business) connector in memory, for testing the price list flow locally."""
from .connector import Excel, ExcelError, encode_column
from .workbook import ExcelDate, Table, Workbook, to_serial

__all__ = ["Excel", "ExcelError", "encode_column", "ExcelDate", "Table", "Workbook", "to_serial"]
