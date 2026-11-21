# Contoso vendor tools

Python 3.11+ command line tools for the Contoso Vendor Management Office. Fictional sample data only.

* Put business logic in `src/vendor_tools/renewals.py`; keep `src/vendor_tools/cli.py` to argument parsing and printing.
* Dates are `datetime.date` objects and ISO 8601 (`YYYY-MM-DD`) in files and output. Never parse dates with locale-dependent formats.
* Money is whole euros (`int`). Do not introduce floats for amounts.
* Add or update tests for every behaviour change. Run `python -m pytest` and report the result.
* Do not add third-party dependencies. The standard library is enough here.
