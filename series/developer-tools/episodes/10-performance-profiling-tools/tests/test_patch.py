"""The slow version as a patch against the healthy source, and the proof that the functional tests cannot see it."""
from __future__ import annotations

import re

from conftest import APP, BUGS, apply_patch, copy_app, needs_dotnet, needs_patch, run

PATCH = "01-load-everything.patch"


@needs_patch
def test_patch_applies_cleanly_and_only_touches_the_report(tmp_path):
    app = copy_app(tmp_path)
    before = (app / "src/Contoso.Orders.Api/Reports.cs").read_text()
    apply_patch(app, PATCH)
    after = (app / "src/Contoso.Orders.Api/Reports.cs").read_text()
    assert before != after
    assert "await db.Orders.ToListAsync(ct)" in after and "AsNoTracking" not in after and "GroupBy(o => o.Customer)" in after
    touched = re.findall(r"^diff --git a/(\S+)", (BUGS / PATCH).read_text(), flags=re.M)
    assert touched == ["src/Contoso.Orders.Api/Reports.cs"]


def test_the_shipped_code_is_the_fast_version():
    reports = (APP / "src/Contoso.Orders.Api/Reports.cs").read_text()
    assert ".Where(o => o.Created >= firstDay && o.Created < nextMonth)" in reports and "AsNoTracking()" in reports
    assert "ToListAsync(ct);" in reports and "everything" not in reports


@needs_dotnet
@needs_patch
def test_with_the_patch_the_functional_tests_stay_green_and_only_the_performance_guards_fail(tmp_path):
    app = copy_app(tmp_path)
    apply_patch(app, PATCH)
    done = run(["dotnet", "test", "-m:1", "--nologo", "-v", "n"], app)
    output = done.stdout + done.stderr
    failed = sorted(set(re.findall(r"Contoso\.Orders\.Api\.Tests\.(\w+\.\w+) \[FAIL\]", output)))
    assert failed == ["ReportPerformanceTests.One_report_stays_inside_its_allocation_budget",
                      "ReportPerformanceTests.The_report_is_one_query_and_the_database_does_the_filtering_and_grouping"], output
    assert done.returncode != 0
    assert re.search(r"one report allocated [\d,]+ bytes for 20,000 orders in the table, the budget is 1,000,000", output)
    # the functional tests, the numbers and the HTTP contract are all still fine
    assert re.search(r"Passed:\s+33\b", output) and re.search(r"Failed:\s+2\b", output), output[-600:]
