import json
from pathlib import Path

import pytest

from tsql_gate.gate import Severity, check_text, exit_code, mask, split_batches
from tsql_gate.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "src" / "samples"
QUERIES = sorted((ROOT / "src" / "queries").glob("q*.sql"))


def rules(findings, severity=None):
    return {f.rule for f in findings if severity is None or f.severity == severity}


# ---- masking and batches ----------------------------------------------------------------------------------------

def test_mask_keeps_length_and_newlines_and_blanks_strings_comments_and_brackets():
    text = "SELECT 'DROP TABLE x' -- DROP\n/* DELETE\nFROM t */ SELECT [Update] FROM \"Drop\".t"
    m = mask(text)
    assert len(m) == len(text) and m.count("\n") == text.count("\n")
    for word in ("DROP", "DELETE", "Update"):
        assert word.lower() not in m.lower().replace("x", "")  # only blanks and the x placeholder remain


def test_mask_handles_escaped_quote_inside_string():
    m = mask("SELECT 'it''s DROP' ; DROP TABLE a.b")
    assert m.count("DROP") == 1


def test_split_batches_on_go_only_when_alone_and_gives_start_lines():
    text = "SELECT 1\nGO\n\nSELECT 2\n/*\nGO\n*/\nSELECT 3\nGO 5\n"
    batches = split_batches(text)
    assert [b.start_line for b in batches] == [1, 3]
    assert "GO" in batches[1].text  # the GO inside the block comment stays in the batch


# ---- the reference queries and the safe examples pass --------------------------------------------------------------

@pytest.mark.parametrize("path", QUERIES, ids=lambda p: p.name)
def test_reference_queries_pass_read_only_with_no_findings(path):
    assert check_text(path.read_text(), mode="readonly") == []


def test_safe_examples_pass_read_only():
    assert check_text((SAMPLES / "safe-examples.sql").read_text()) == []


# ---- write rules ---------------------------------------------------------------------------------------------------

def test_update_without_where_is_blocked_in_both_modes():
    sql = "UPDATE Sales.Orders SET Status = N'x';"
    for mode in ("readonly", "readwrite"):
        assert "TG-W002" in rules(check_text(sql, mode), Severity.BLOCK)


def test_update_with_where_is_a_write_only_in_readonly_mode():
    sql = "UPDATE Sales.Orders SET Status = N'x' WHERE OrderId = 1;"
    assert "TG-W001" in rules(check_text(sql, "readonly"), Severity.BLOCK)
    assert check_text(sql, "readwrite") == []


def test_delete_without_where_and_update_from_with_alias():
    assert "TG-W002" in rules(check_text("DELETE FROM Sales.Orders;", "readwrite"))
    ok = ("UPDATE o SET Status = N'x' FROM Sales.Orders AS o JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId "
          "WHERE c.Region = N'North';")
    assert check_text(ok, "readwrite") == []  # alias target is not flagged as an unqualified table


def test_cte_delete_without_where_is_found_inside_the_statement():
    sql = "WITH x AS (SELECT OrderId FROM Sales.Orders) DELETE FROM Sales.OrderLines;"
    assert "TG-W002" in rules(check_text(sql, "readwrite"))


def test_truncate_always_blocked_and_drop_needs_if_exists():
    assert "TG-W003" in rules(check_text("TRUNCATE TABLE Sales.Orders;", "readwrite"), Severity.BLOCK)
    assert "TG-W003" in rules(check_text("DROP TABLE Sales.Orders;", "readwrite"), Severity.BLOCK)
    f = check_text("DROP TABLE IF EXISTS Sales.Orders;", "readwrite")
    assert exit_code(f) == 1 and "TG-W003" in rules(f, Severity.WARN)


def test_select_into_is_flagged_but_insert_into_is_not_a_select_into():
    assert "TG-W004" in rules(check_text("SELECT CustomerId INTO #t FROM Sales.Customers;", "readwrite"))
    assert "TG-W004" not in rules(check_text("INSERT INTO #t (a) SELECT CustomerId FROM Sales.Customers;", "readwrite"))


def test_permissions_blocked_readonly_warn_readwrite():
    sql = "GRANT SELECT ON SCHEMA::Sales TO PUBLIC;"
    assert "TG-S002" in rules(check_text(sql, "readonly"), Severity.BLOCK)
    assert "TG-S002" in rules(check_text(sql, "readwrite"), Severity.WARN)
    assert "TG-S002" in rules(check_text("ALTER ROLE db_owner ADD MEMBER bob;", "readwrite"), Severity.WARN)


# ---- dangerous features, dynamic SQL, EXEC ---------------------------------------------------------------------------

def test_xp_cmdshell_and_sp_configure_blocked_even_in_readwrite():
    f = check_text("EXEC xp_cmdshell 'dir';\nEXEC sp_configure 'xp_cmdshell', 1;", "readwrite")
    assert "TG-S001" in rules(f, Severity.BLOCK)
    assert exit_code(f) == 2


def test_dangerous_words_inside_strings_and_comments_are_ignored():
    sql = "SELECT 'xp_cmdshell and DROP TABLE x' AS note; -- EXEC xp_cmdshell 'dir'\n/* TRUNCATE TABLE a.b */"
    assert check_text(sql, "readonly") == []


def test_dynamic_sql_with_variable_blocked_readonly_warn_readwrite():
    sql = "DECLARE @s nvarchar(max) = N'SELECT 1';\nEXEC (@s);"
    assert "TG-D001" in rules(check_text(sql, "readonly"), Severity.BLOCK)
    assert "TG-D001" in rules(check_text(sql, "readwrite"), Severity.WARN)


def test_exec_of_a_literal_string_is_analysed_recursively():
    f = check_text("EXEC ('DELETE FROM Sales.Orders');", "readwrite")
    assert "TG-W002" in rules(f, Severity.BLOCK)
    assert any("inside dynamic SQL" in x.message for x in f)


def test_sp_executesql_literal_is_analysed():
    f = check_text("EXEC sp_executesql N'TRUNCATE TABLE Sales.Orders';", "readwrite")
    assert "TG-W003" in rules(f, Severity.BLOCK)


def test_exec_of_unknown_procedure_is_not_assumed_read_only():
    assert "TG-E001" in rules(check_text("EXEC Sales.GetTopCustomers @n = 5;", "readonly"), Severity.BLOCK)
    assert "TG-E001" in rules(check_text("EXEC Sales.GetTopCustomers @n = 5;", "readwrite"), Severity.WARN)
    assert check_text("EXEC sp_help N'Sales.Orders'; EXEC sp_spaceused;", "readonly") == []


# ---- style rules (the constitution asks for these) ---------------------------------------------------------------

def test_select_star_flagged_but_count_star_and_exists_star_are_not():
    assert "TG-Q001" in rules(check_text("SELECT * FROM Sales.Orders;"))
    assert "TG-Q001" in rules(check_text("SELECT o.* FROM Sales.Orders AS o;"))
    ok = ("SELECT COUNT(*) AS n FROM Sales.Orders AS o WHERE EXISTS (SELECT * FROM Sales.OrderLines AS l "
          "WHERE l.OrderId = o.OrderId);")
    assert check_text(ok) == []


def test_unqualified_tables_flagged_but_cte_temp_and_variables_are_not():
    assert "TG-Q002" in rules(check_text("SELECT OrderId FROM Orders;"))
    ok = ("WITH recent AS (SELECT OrderId FROM Sales.Orders) SELECT r.OrderId FROM recent AS r;\n"
          "SELECT 1 AS a INTO #t;\nSELECT a FROM #t;")
    assert "TG-Q002" not in rules(check_text(ok, "readwrite"))


# ---- parsing --------------------------------------------------------------------------------------------------------

def test_unparseable_batch_fails_closed():
    f = check_text("SELEC FROM WHERE;")
    assert "TG-P001" in rules(f, Severity.BLOCK)


def test_backup_is_a_write_and_unparsed():
    f = check_text("BACKUP DATABASE ContosoCopilot TO DISK = 'x.bak';")
    assert {"TG-W001", "TG-P001"} <= rules(f, Severity.BLOCK)


def test_statements_without_semicolons_still_parse():
    sql = "SELECT CustomerId FROM Sales.Customers\nSELECT OrderId FROM Sales.Orders\n"
    assert check_text(sql) == []


def test_insert_select_on_two_lines_is_not_split():
    sql = "INSERT INTO #t (a)\nSELECT CustomerId FROM Sales.Customers\n"
    assert "TG-P001" not in rules(check_text(sql, "readwrite"))


def test_line_numbers_follow_the_file_across_batches():
    sql = "SELECT 1\nGO\n\n\nUPDATE Sales.Orders SET Status = N'x';\nGO\n"
    f = [x for x in check_text(sql) if x.rule == "TG-W002"]
    assert f and f[0].line == 5


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        check_text("SELECT 1", mode="yolo")


# ---- the risky samples (one expectation per batch) -----------------------------------------------------------------------

def test_risky_examples_each_batch_is_caught():
    f = check_text((SAMPLES / "risky-examples.sql").read_text(), "readwrite")
    by_line = {}
    for x in f:
        by_line.setdefault(x.line, set()).add(x.rule)
    assert "TG-W002" in by_line[5]
    assert {"TG-Q001", "TG-Q002"} <= by_line[8]
    assert "TG-W003" in by_line[11] and "TG-W003" in by_line[12]
    assert "TG-S001" in by_line[15] and "TG-S001" in by_line[17]
    assert "TG-D001" in by_line[22]
    assert "TG-S002" in by_line[25] and "TG-S002" in by_line[26]
    assert exit_code(f) == 2


# ---- command line ----------------------------------------------------------------------------------------------------

def test_cli_exit_codes_and_json(capsys):
    assert main(["check", str(SAMPLES / "safe-examples.sql")]) == 0
    assert main(["check", str(SAMPLES / "risky-examples.sql")]) == 2
    capsys.readouterr()
    assert main(["check", str(SAMPLES / "risky-examples.sql"), "--json"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data[0]["mode"] == "readonly" and data[0]["findings"][0]["rule"].startswith("TG-")


def test_cli_warning_only_exit_code_1(tmp_path):
    p = tmp_path / "q.sql"
    p.write_text("SELECT * FROM Sales.Orders;")
    assert main(["check", str(p)]) == 1
