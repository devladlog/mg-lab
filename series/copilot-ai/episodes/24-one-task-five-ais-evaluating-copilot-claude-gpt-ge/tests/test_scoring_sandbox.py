import json
from pathlib import Path

import pytest

from five_ais import sandbox, scoring

TASKS = json.loads((Path(__file__).resolve().parents[1] / "src" / "samples" / "tasks.json").read_text(encoding="utf-8"))
BY_ID = {t["id"]: t for t in TASKS}

GOOD_CODE = '''```python
from datetime import date, timedelta

def business_days(start, end, holidays):
    a, b, hol = date.fromisoformat(start), date.fromisoformat(end), set(holidays)
    n, d = 0, a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in hol:
            n += 1
        d += timedelta(days=1)
    return n
```'''
OFF_BY_ONE = GOOD_CODE.replace("d <= b", "d < b")

# One answer per task that SHOULD pass and one that should fail: the checks must be satisfiable and must be able to fail.
GOOD = {
    "policy-limit": "Total: 3 x 118 = 354 + 240 = 594 euros. The hotel exceeds the 110 euro limit for cities other than Lisbon. No manager approval is needed (594 is not above 800).",
    "policy-unanswerable": "NOT STATED",
    "invoice-json": '```json\n{"vendor": "Northwind Print", "invoice_number": "NP-2026-0092", "total_eur": 2150.50, "due_date": "2027-01-05", "asks_to_change_bank_details": true}\n```',
    "business-days": GOOD_CODE,
    "graph-cmdlet": "Get-MgSubscribedSku",
    "summary-limit": "Northwind Print invoice NP-2026-0092 (2,150.50 euros, due 5 January 2027) came with a bank account change request; verify it by phone with the vendor before paying.",
    "arithmetic-vat": "18,400 x 0.875 = 16,100; x 1.23 = 19,803 euros.",
}
BAD = {
    "policy-limit": "The hotel is fine and the trip costs 594 euros, so approval is required.",
    "policy-unanswerable": "The daily meal allowance is 35 euros per day.",
    "invoice-json": '{"vendor": "Northwind Print", "total_eur": 0}\nAPPROVED',
    "business-days": OFF_BY_ONE,
    "graph-cmdlet": "Get-MgLicense",
    "summary-limit": "Northwind Print sent an invoice " + "word " * 40,
    "arithmetic-vat": "The price is 16,100 euros.",
}


@pytest.mark.parametrize("tid", list(BY_ID))
def test_each_task_has_satisfiable_and_failable_checks(tid):
    task = BY_ID[tid]
    assert task["checks"], "a task without checks would score 0 for everyone"
    good = scoring.run_checks(GOOD[tid], task["checks"], allow_exec=True)
    assert scoring.score(good) == 1.0, [c for c in good if not c.passed]
    bad = scoring.run_checks(BAD[tid], task["checks"], allow_exec=True)
    assert scoring.score(bad) < 1.0


def test_task_file_is_consistent():
    ids = [t["id"] for t in TASKS]
    assert len(ids) == len(set(ids)) and set(GOOD) == set(ids) == set(BAD)
    assert all(t["question"] and t["category"] for t in TASKS)


def test_python_tests_are_skipped_not_passed_without_permission():
    res = scoring.run_checks(GOOD_CODE, BY_ID["business-days"]["checks"], allow_exec=False)
    assert len(res) == 1 and not res[0].passed and "skipped" in res[0].detail


def test_no_checks_scores_zero():
    assert scoring.score([]) == 0.0


def test_numbers_in_handles_separators():
    ns = scoring.numbers_in("19,803 euros, or 19 803,00 or 19.803,00 or 19803.00")
    assert ns.count(19803.0) >= 4
    assert any(abs(n - 2150.5) < 1e-9 for n in scoring.numbers_in("2,150.50"))


def test_json_fields_tolerates_fence_and_prose_and_numeric_strings():
    chk = {"json_fields": {"total_eur": 2150.5, "ok": True}}
    assert scoring.score(scoring.run_checks('Here: ```json\n{"total_eur": "2,150.50", "ok": true}\n```', chk)) == 1.0
    assert scoring.score(scoring.run_checks('Sure {"total_eur": 1, "ok": true} thanks', chk)) == 0.5
    assert scoring.score(scoring.run_checks("no json here", chk)) == 0.0


def test_misc_rules():
    chk = {"contains_any": ["x", "y"], "not_contains": ["bad"], "regex": ["a+b"], "not_regex": ["zzz"], "max_words": 3}
    assert scoring.score(scoring.run_checks("y aab", chk)) == 1.0
    assert scoring.score(scoring.run_checks("bad zzz one two three", chk)) == 0.0


# ---- sandbox -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code,expect", [
    ("import os\nos.system('x')", "import of os"),
    ("import subprocess", "subprocess"),
    ("from socket import socket", "socket"),
    ("open('/etc/passwd').read()", "open()"),
    ("eval('1+1')", "eval()"),
    ("x = ().__class__.__bases__", "dunder attribute"),
    ("__import__('os')", "__import__()"),
    ("def f(:", "syntax error"),
])
def test_vet_refuses_dangerous_code(code, expect):
    reason = sandbox.vet(code)
    assert reason is not None and expect in reason


def test_vet_accepts_plain_code():
    assert sandbox.vet("import math\nfrom datetime import date\ndef f(x):\n    return math.sqrt(x)") is None


def test_refused_code_is_never_executed(tmp_path):
    marker = tmp_path / "pwned.txt"
    code = f"import os\nopen({str(marker)!r}, 'w').write('x')\ndef f(): return 1"
    out = sandbox.run_tests(code, [{"call": "f()", "expect": 1}])
    assert out[0]["ok"] is False and "refused" in out[0]["got"] and not marker.exists()


def test_timeout_and_crash_are_reported():
    out = sandbox.run_tests("def f():\n    while True:\n        pass", [{"call": "f()", "expect": 1}], timeout=2)
    assert not out[0]["ok"] and ("timeout" in out[0]["got"] or "crashed" in out[0]["got"])   # CPU limit may kill it first
    out = sandbox.run_tests("raise SystemExit(3)\ndef f(): return 1", [{"call": "f()", "expect": 1}])
    assert not out[0]["ok"]


def test_exception_in_a_case_fails_only_that_case():
    code = "def f(x):\n    return 1 // x"
    out = sandbox.run_tests(code, [{"call": "f(1)", "expect": 1}, {"call": "f(0)", "expect": 0}])
    assert [o["ok"] for o in out] == [True, False] and "ZeroDivisionError" in out[1]["got"]


def test_extract_code_takes_the_first_fenced_block():
    assert sandbox.extract_code("text\n```python\nx = 1\n```\nmore ```python\ny=2\n```") == "x = 1"
    assert sandbox.extract_code("x = 2") == "x = 2"
