"""The local half: the injection and inference mechanics executed on DuckDB, and every expected/ file checked
against an independent reading of the seed data and of the documented behaviour (masking format, error 229)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import labdb  # noqa: E402
import security_lab as lab  # noqa: E402

SEED = lab.sql_text("01-schema-and-data.sql")
CUSTOMERS = [(int(i), n, e, r) for i, n, e, r in
             re.findall(r"\((\d), N'([^']+)',\s+N'([^']+)',\s+N'(\w+)'\)", SEED)]
PAYLOAD = "' OR 1 = 1 --"


def expected(key):
    return labdb.read_csv(ROOT / "expected" / f"{key}.csv")


def test_seed_customers_parsed():
    assert len(CUSTOMERS) == 6 and {c[3] for c in CUSTOMERS} == {"North", "Centre", "South"}


def test_local_run_matches_expected(capsys):
    assert lab.run_local() == 0
    out = capsys.readouterr().out
    assert "LIKE N'' OR 1 = 1 --%' ORDER BY CustomerId;" in out      # the SQL text the payload produces


@pytest.mark.parametrize("expr,vars_,want", [
    ("N'a''b' + @x + N'c';", {"x": "Z"}, "a'bZc"),
    ("N'ORDER BY ' + QUOTENAME(@s) + N';'", {"s": "Na]me"}, "ORDER BY [Na]]me];"),
    ("N'x'\n        + @y + N'%'' z';", {"y": "1"}, "x1%' z"),
])
def test_eval_concat(expr, vars_, want):
    assert lab.eval_concat(expr, vars_) == want


def test_eval_concat_refuses_what_it_doesnt_understand():
    with pytest.raises(ValueError):
        lab.eval_concat("N'a' + UPPER(@x)", {"x": "b"})


def test_step_inputs_are_read_from_the_step_files():
    assert lab.step_inputs("s02-injection-unsafe") == ["Alex", PAYLOAD]
    assert lab.step_inputs("s04-signed-search") == ["Alex", PAYLOAD]
    assert lab.step_inputs("s03-dynamic-sql-breaks-chain") == ["Alex", PAYLOAD]


def test_unsafe_text_changes_meaning_safe_text_does_not():
    unsafe = lab.eval_concat(lab.sql_builder("Sales.usp_SearchCustomers_Unsafe"), {"NamePrefix": PAYLOAD})
    assert "OR 1 = 1 --" in unsafe
    safe = lab.eval_concat(lab.sql_builder("Sales.usp_SearchCustomers"), {"NamePrefix": PAYLOAD, "SortBy": "CustomerId"})
    assert PAYLOAD not in safe and "LIKE @prefix + N'%' ORDER BY [CustomerId];" in safe
    duck = labdb.transpile(safe)[0]
    assert "$prefix + N'%'" in duck                   # the one spot local_search rewrites for DuckDB


def test_injection_counts_follow_from_the_data():
    assert expected("s02-injection-unsafe")[1:] == [
        ["Alex", str(sum(c[1].startswith("Alex") for c in CUSTOMERS))], [PAYLOAD, str(len(CUSTOMERS))]]
    assert [r[3] for r in expected("s04-signed-search")[1:]] == ["1", "0"]


def masked_email(email: str) -> str:
    # Learn: the email() mask exposes the first letter and the constant suffix ".com": aXXX@XXXX.com
    return email[0] + "XXX@XXXX.com"


def test_masking_expectation_follows_the_documented_format():
    want = [[n, masked_email(e), e] for i, n, e, r in CUSTOMERS if i <= 3]
    assert expected("s07-masking")[1:] == want


def test_inference_counts_follow_from_the_data():
    def like(value, pattern):            # the guesses only use a trailing %
        return value.startswith(pattern.rstrip("%"))
    for guess, n in expected("s08-masking-inference")[1:]:
        assert int(n) == sum(like(c[2], guess) for c in CUSTOMERS), guess


def test_rls_expectation_follows_from_the_region_map():
    rls = lab.sql_text("15-row-level-security.sql")
    regions = {}
    for user, region in re.findall(r"\(N'(\w+)', N'(\w+)'\)", rls):
        regions.setdefault(user, set()).add(region)
    rows = expected("s05-row-level-security")[1:]

    def seen(regs):
        hits = [c for c in CUSTOMERS if c[3] in regs]
        return [str(len(hits)), ", ".join(sorted({c[3] for c in hits})) or "NULL"]
    assert rows[0][2:] == seen(regions["sales_north"])
    assert rows[1][2:] == seen(regions["sales_south"])
    assert rows[2][2:] == seen({"North", "Centre", "South"})            # db_owner bypass
    bruno = [c for c in CUSTOMERS if c[1].startswith("Bruno")]
    assert rows[3][2:] == seen(regions["sales_north"] & {c[3] for c in bruno})


def test_permission_denials_use_error_229():
    # Learn: "Msg 229 ... The SELECT permission was denied on the object ..."
    assert [r[3] for r in expected("s01-least-privilege")[1:]] == ["error 229", "6 rows", "error 229"]
    assert [r[4] for r in expected("s03-dynamic-sql-breaks-chain")[1:]] == ["229", "229"]
    assert expected("s06-rls-place-order")[3][3] == "error 229"
    assert expected("s06-rls-place-order")[2][3] == "error 50001: Unknown customer."     # episode 5's THROW


def test_every_step_has_files():
    for s in lab.STEPS:
        assert (ROOT / "expected" / f"{s.key}.csv").exists() and (ROOT / "src" / "sql" / f"{s.key}.sql").exists()
        for f in s.before:
            assert (ROOT / "src" / "sql" / f).exists()
    for f in lab.SETUP_FILES:
        assert (ROOT / "src" / "sql" / f).exists()
