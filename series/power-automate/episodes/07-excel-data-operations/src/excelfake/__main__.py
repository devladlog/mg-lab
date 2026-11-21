"""python -m excelfake                     the import, as the solution's flow does it
python -m excelfake --no-pagination     draft 1: List rows with default settings
python -m excelfake --serial-dates      draft 2: no DateTime Format
python -m excelfake --unencoded         draft 3: item()?['Item No.'] typed by hand
python -m excelfake --row-by-row        draft 4: Apply to each + Get/Update/Add a row
python -m excelfake --rows 6000         a supplier file with 6000 rows (more than the pagination threshold)
python -m excelfake make-workbooks DIR  write the two real .xlsx files for the lab"""
import argparse
import sys
from pathlib import Path

from flowkit import load_flow

from . import scenario, variants


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["make-workbooks"]:
        out = Path(argv[1] if len(argv) > 1 else "out")
        print(scenario.price_list().save_xlsx(out / scenario.PRICE_FILE))
        print(scenario.catalogue().save_xlsx(out / scenario.CATALOGUE_FILE))
        return 0
    p = argparse.ArgumentParser(prog="excelfake", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-pagination", action="store_true")
    p.add_argument("--serial-dates", action="store_true")
    p.add_argument("--unencoded", action="store_true")
    p.add_argument("--row-by-row", action="store_true")
    p.add_argument("--rows", type=int)
    a = p.parse_args(argv)
    flow = load_flow(scenario.FLOW_PATH)
    for flag, fn in (("no_pagination", variants.no_pagination), ("serial_dates", variants.serial_dates),
                     ("unencoded", variants.unencoded_column), ("row_by_row", variants.row_by_row)):
        if getattr(a, flag):
            flow = fn(flow)
    price_wb = scenario.big_price_list(a.rows) if a.rows else None
    o = scenario.run_import(flow, price_wb=price_wb)
    print(scenario.describe(o))
    return 0 if o.run.status == "Succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
