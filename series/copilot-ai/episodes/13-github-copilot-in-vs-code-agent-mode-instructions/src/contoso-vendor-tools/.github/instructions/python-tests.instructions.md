---
name: 'Python tests'
description: 'Use when creating or updating Python tests.'
applyTo: 'tests/**/*.py'
---
* Name tests `test_<behavior>_<condition>`.
* Use the sample file `data/vendors.csv` for realistic data; do not invent vendors in tests.
* Pass `today` explicitly. Never call `date.today()` inside a test.
* Run `python -m pytest <test-file>` after changing a test.
