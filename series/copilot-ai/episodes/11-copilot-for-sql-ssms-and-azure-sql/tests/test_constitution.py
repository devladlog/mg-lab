from pathlib import Path

import pytest

from tsql_gate.cli import main
from tsql_gate.constitution import lint_constitution, parse_constitution, render_tsql

ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = (ROOT / "src" / "CONSTITUTION.md").read_text(encoding="utf-8")
LEARN_EXAMPLE = """---
agentExecuteAsUser: ReportingUser

---
Any T-SQL generated for this database must comply with organizational standards.
Queries must not use SELECT *. Always use explicit column lists.
"""


def test_parse_front_matter_and_body():
    c = parse_constitution(CONSTITUTION)
    assert c.execute_as_user == "GHCP_DB_User"
    assert c.body.lstrip().startswith("## Database constitution")


def test_learn_example_has_the_documented_shape():
    c = parse_constitution(LEARN_EXAMPLE)
    assert c.execute_as_user == "ReportingUser"
    assert lint_constitution(LEARN_EXAMPLE) == []


def test_the_episode_constitution_lints_clean():
    assert lint_constitution(CONSTITUTION) == []


@pytest.mark.parametrize("user", ["sa", "dbo", "[dbo]", "db_owner"])
def test_privileged_execute_as_users_are_reported(user):
    text = f"---\nagentExecuteAsUser: {user}\n---\nbody"
    assert any("highly privileged" in p for p in lint_constitution(text))


def test_privileged_looking_name_and_missing_front_matter_and_unknown_keys():
    assert any("looks privileged" in p for p in lint_constitution("---\nagentExecuteAsUser: SalesAdmin\n---\nx"))
    assert any("no YAML front matter" in p for p in lint_constitution("just a body"))
    assert any("no agentExecuteAsUser" in p for p in lint_constitution("---\nfoo: bar\n---\nx"))
    assert any("not documented" in p for p in lint_constitution("---\nagentExecuteAsUser: G\nmode: x\n---\nx"))
    assert any("empty body" in p for p in lint_constitution("---\nagentExecuteAsUser: G\n---\n"))


def test_render_matches_learn_procedure_and_escapes_quotes():
    sql = render_tsql("---\nagentExecuteAsUser: G\n---\nDon't use SELECT *.", "SalesDB")
    assert "EXECUTE sp_addextendedproperty" in sql
    assert "@name = N'CONSTITUTION.md'" in sql
    assert "Don''t use SELECT *." in sql
    assert sql.startswith("USE [SalesDB];\nGO\n")
    assert "sp_updateextendedproperty" in render_tsql("---\nagentExecuteAsUser: G\n---\nx", "SalesDB", update=True)


def test_render_rejects_odd_database_names():
    with pytest.raises(ValueError):
        render_tsql(CONSTITUTION, "x]; DROP DATABASE y; --")


def test_committed_03_script_is_what_the_tool_generates():
    expected = render_tsql(CONSTITUTION, "ContosoCopilot")
    assert (ROOT / "src" / "sql" / "03-constitution.sql").read_text(encoding="utf-8") == expected


def test_cli_constitution_lint_and_sql(capsys):
    assert main(["constitution", "lint", str(ROOT / "src" / "CONSTITUTION.md")]) == 0
    assert "GHCP_DB_User" in capsys.readouterr().out
    assert main(["constitution", "sql", str(ROOT / "src" / "CONSTITUTION.md"), "--database", "ContosoCopilot"]) == 0
    assert "sp_addextendedproperty" in capsys.readouterr().out


def test_constitution_larger_than_the_extended_property_limit_is_reported():
    big = "---\nagentExecuteAsUser: G\n---\n" + ("x" * 3800)
    assert any("7500 bytes" in p for p in lint_constitution(big))
    assert not any("7500 bytes" in p for p in lint_constitution(CONSTITUTION))
