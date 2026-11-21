"""The monthly ERP exports: deterministic, and messy in exactly the documented ways."""
import csv
import filecmp
from pathlib import Path

import pytest

from generate_export import HEADER, generate
from make_monthly_exports import build_files, write

EXPORTS = Path(__file__).resolve().parents[1] / "src" / "data" / "exports"


@pytest.fixture(scope="module")
def files():
    return build_files([[str(x) for x in r] for r in generate(42)])


def read(name):
    with (EXPORTS / name).open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f, delimiter=";"))


def test_committed_exports_are_byte_identical_to_a_fresh_run(tmp_path, files):
    write(files, tmp_path)
    committed = sorted(p.name for p in EXPORTS.iterdir())
    assert committed == sorted(p.name for p in tmp_path.iterdir())
    match, mismatch, errors = filecmp.cmpfiles(EXPORTS, tmp_path, committed, shallow=False)
    assert not mismatch and not errors


def test_24_monthly_csv_files_and_one_stray_text_file():
    names = sorted(p.name for p in EXPORTS.iterdir())
    assert names[0] == "_README.txt"
    assert names[1:] == [f"sales_{y}-{m:02d}.csv" for y in (2024, 2025) for m in range(1, 13)]


def test_erp_format_semicolons_crlf_no_bom():
    raw = (EXPORTS / "sales_2024-03.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.split(b"\r\n")[0].decode() == ";".join(HEADER)
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_portuguese_number_and_date_formats():
    row = read("sales_2024-01.csv")[1]
    assert row[2] == "01/01/2024" and row[3] == "05/01/2024"         # dd/MM/yyyy
    assert row[17] == "40,41" and row[18] == "17,00"                 # decimal comma
    assert all("." not in r[17] for r in read("sales_2025-06.csv")[1:-1])


def test_every_file_ends_with_a_total_row_of_19_fields():
    for p in EXPORTS.glob("*.csv"):
        rows = read(p.name)
        assert rows[-1][0] == "TOTAL" and len(rows[-1]) == 19
        assert int(rows[-1][16]) == sum(int(r[16]) for r in rows[1:-1])


def test_online_product_codes_are_lower_case_with_a_trailing_space():
    rows = [r for p in EXPORTS.glob("*.csv") for r in read(p.name)[1:-1]]
    online = [r for r in rows if r[10] == "Online"]
    assert online and all(r[11] == r[11].lower() and r[11].endswith(" ") for r in online)
    assert all(r[11] == r[11].upper().strip() for r in rows if r[10] == "Store")


def test_overlap_lines_appear_twice_and_some_were_corrected(files):
    seen = {}
    for name, rows in files.items():
        for r in rows:
            seen.setdefault((r[0], r[1]), []).append((name, r[16]))
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    assert len(dupes) == 247
    assert all(len(v) == 2 and v[0][0] < v[1][0] for v in dupes.values())
    corrected = [v for v in dupes.values() if v[0][1] != v[1][1]]
    assert 0 < len(corrected) < len(dupes)
    assert all(int(old) == int(new) + 1 for (_, old), (_, new) in corrected)   # the older file has the draft


def test_guest_orders_have_an_empty_customer_code():
    rows = [r for p in EXPORTS.glob("*.csv") for r in read(p.name)[1:-1]]
    guests = [r for r in rows if r[4] == ""]
    assert guests and all(r[5] == "" for r in guests)
