#!/usr/bin/env python3
"""Split the Contoso Bikes sales export (episode 1) into the monthly files a real ERP drops in a folder.

Same order lines as episode 1 (generate_export.py, seed 42), but delivered the way they usually arrive:

  * one file per month:  exports/sales_2024-01.csv ... exports/sales_2025-12.csv
  * semicolon separated, Portuguese formats: decimal comma (47,40) and day/month/year dates (05/01/2024)
  * CRLF line endings, UTF-8 without BOM
  * a TOTAL footer row at the end of every file
  * the online shop writes product codes in lower case with a trailing space ("bk-r-100 ")
  * guest orders have an empty customer code
  * each file re-exports the last OVERLAP_DAYS days of the previous month, because late corrections
    land there. The older file still holds the pre-correction quantity for some of those lines,
    so the same (OrderNumber, LineNumber) appears twice with different values: the newest file wins.
  * a stray _README.txt in the folder (not a CSV)

The Power Query queries in ../queries turn this folder back into the star schema of episode 1.

Usage:
    python make_monthly_exports.py [--out exports]
"""
import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from generate_export import HEADER, generate

OVERLAP_DAYS = 2


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def is_draft(order_number: str) -> bool:
    """Lines whose quantity was corrected after the first export (deterministic: every third order)."""
    return int(order_number[2:]) % 3 == 0


def to_erp_row(r, draft=False):
    """One episode-1 row (ISO dates, decimal point) -> ERP formats."""
    order, line, od, sd, ccode, cname, ccity, ccountry, store, scountry, channel, \
        pcode, pname, sub, cat, color, qty, price, cost = r
    if channel == "Online":
        pcode = pcode.lower() + " "
    qty = int(qty) + (1 if draft else 0)
    dmy = lambda iso: date.fromisoformat(iso).strftime("%d/%m/%Y")
    comma = lambda s: s.replace(".", ",")
    return [order, line, dmy(od), dmy(sd), ccode, cname, ccity, ccountry, store, scountry, channel,
            pcode, pname, sub, cat, color, qty, comma(price), comma(cost)]


def build_files(rows):
    """Return {file name: [erp rows]} in file order."""
    months = sorted({month_key(date.fromisoformat(r[2])) for r in rows})
    files = {}
    for i, m in enumerate(months):
        own = [r for r in rows if month_key(date.fromisoformat(r[2])) == m]
        y, mo = map(int, m.split("-"))
        first_day = date(y, mo, 1)
        overlap = []
        if i > 0:
            start = first_day - timedelta(days=OVERLAP_DAYS)
            overlap = [r for r in rows if start <= date.fromisoformat(r[2]) < first_day]
        # the overlap lines in THIS file are final; the copy in the previous file was the draft
        files[f"sales_{m}.csv"] = [to_erp_row(r) for r in overlap] + [to_erp_row(r) for r in own]
    # second pass: replace, in each file, the lines that the NEXT file re-exports by their draft version
    names = list(files)
    for i, name in enumerate(names[:-1]):
        nxt = names[i + 1]
        y, mo = map(int, nxt[6:13].split("-"))
        start = date(y, mo, 1) - timedelta(days=OVERLAP_DAYS)
        reexported = {(r[0], r[1]) for r in rows if start <= date.fromisoformat(r[2]) < date(y, mo, 1)}
        src = {(r[0], r[1]): r for r in rows}
        files[name] = [to_erp_row(src[(e[0], e[1])], draft=is_draft(e[0]))
                       if (e[0], e[1]) in reexported else e for e in files[name]]
    return files


def write(files, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, erp_rows in files.items():
        with (out_dir / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\r\n")
            w.writerow(HEADER)
            w.writerows(erp_rows)
            total = [""] * len(HEADER)
            total[0] = "TOTAL"
            total[HEADER.index("Quantity")] = sum(int(r[16]) for r in erp_rows)
            w.writerow(total)
    (out_dir / "_README.txt").write_text(
        "Monthly sales exports from the Contoso Bikes ERP land in this folder.\r\n", encoding="utf-8")
    return len(files)


def main():
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(here / "exports"))
    a = ap.parse_args()
    rows = [[str(x) for x in r] for r in generate(42)]
    files = build_files(rows)
    n = write(files, Path(a.out))
    lines = sum(len(v) for v in files.values())
    print(f"wrote {n} monthly files ({lines} order lines, {lines - len(rows)} re-exported) + _README.txt")


if __name__ == "__main__":
    main()
