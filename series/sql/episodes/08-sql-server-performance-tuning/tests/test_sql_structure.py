"""Every script parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar) plus the claims the episode
makes: the diagnosis reads only DMVs, the blocker never commits, RCSI is switched on with ROLLBACK IMMEDIATE and off
again at tear-down, and the Tune objects live in their own schema."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import perf_lab as lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")

SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODE4 = ROOT.parent / "04-query-optimization"


def statements(name):
    return [st for b in tsqlparse.parse_all_sql()[name]["batches"] for st in b["statements"]]


def types(name):
    return [st["type"] for st in statements(name)]


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert statements(name)


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("SELECT TOP (@Top FROM Tune.WaitSnapshot;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not EPISODE4.exists(), reason="episode 4 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode4():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODE4 / "src" / "sql" / "01-schema-and-data.sql").read_bytes()
    assert (SQL / "00-create-database.sql").read_bytes() == (EPISODE4 / "src" / "sql" / "00-create-database.sql").read_bytes()


@pytest.mark.skipif(not (ROOT.parent / "07-backup-recovery").exists(), reason="episode 7 folder not present")
@pytest.mark.parametrize("rel", ["tools/TsqlParse/Program.cs", "tools/TsqlParse/TsqlParse.csproj"])
def test_parser_tool_is_the_same_as_episode7(rel):
    assert (ROOT / rel).read_bytes() == (ROOT.parent / "07-backup-recovery" / rel).read_bytes()


def test_tune_objects_are_in_their_own_schema_and_both_procedures_exist():
    names = sorted(tsqlparse.modules())
    assert names == ["Tune.usp_TakeWaitSnapshot", "Tune.usp_WaitDelta"]
    text = (SQL / "10-tune-tools.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE Tune.WaitSnapshot" in text and "sys.dm_os_wait_stats" in text


def test_the_delta_is_a_difference_not_a_raw_read_and_the_ranking_is_a_watch_list():
    q = lab.extract_delta_query()
    assert "e.WaitTimeMs - ISNULL(b.WaitTimeMs, 0)" in q and "ORDER BY WaitTimeMsDelta DESC" in q
    for w in ("LCK_M_", "PAGEIOLATCH_", "PAGELATCH_", "WRITELOG", "SOS_SCHEDULER_YIELD", "CXPACKET", "CXCONSUMER",
              "ASYNC_NETWORK_IO", "RESOURCE_SEMAPHORE", "THREADPOOL"):
        assert w in q, w
    assert "NOT IN" not in q.upper()            # a watch list, not an exclusion list


def test_read_only_scripts_only_select_or_exec():
    for f in ("t01-config-review.sql", "t02-top-queries.sql", "t03b-reader.sql", "t03c-diagnose.sql"):
        assert set(types(f)) == {"SelectStatement"}, f
    for f in ("t04-wait-delta.sql", "t04b-wait-delta-after-rcsi.sql"):
        assert types(f) == ["ExecuteStatement"], f


def test_diagnosis_reads_the_dmvs_the_episode_names():
    text = (SQL / "t03c-diagnose.sql").read_text(encoding="utf-8")
    for dmv in ("sys.dm_exec_requests", "sys.dm_exec_sql_text", "sys.dm_exec_sessions", "sys.dm_exec_connections"):
        assert dmv in text, dmv
    assert "blocking_session_id" in text and "most_recent_sql_handle" in text and "KILL" not in text.upper().replace("KILLED", "")


def test_blocker_opens_a_transaction_and_never_commits():
    assert types("t03a-blocker.sql") == ["BeginTransactionStatement", "UpdateStatement"]
    assert types("t03d-release.sql") == ["RollbackTransactionStatement"]
    body = "\n".join(l for l in (SQL / "t03a-blocker.sql").read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
    assert "COMMIT" not in body.upper()


def test_rcsi_on_uses_rollback_immediate_and_cleanup_turns_it_off():
    on = (SQL / "t03e-enable-rcsi.sql").read_text(encoding="utf-8")
    assert re.search(r"SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;", on)
    off = (SQL / "t05-cleanup.sql").read_text(encoding="utf-8")
    assert re.search(r"SET READ_COMMITTED_SNAPSHOT OFF WITH ROLLBACK IMMEDIATE;", off)
    assert types("t05-cleanup.sql")[0] == "AlterDatabaseSetStatement"


def test_workload_clears_only_this_databases_plan_cache():
    assert types("w01-workload.sql")[0] == "AlterDatabaseScopedConfigurationClearStatement"
    text = (SQL / "w01-workload.sql").read_text(encoding="utf-8")
    assert "DBCC FREEPROCCACHE" not in text.upper() and "CLEAR PROCEDURE_CACHE" in text.upper()


def test_query_stats_step_cuts_the_statement_out_of_the_batch_text():
    text = (SQL / "t02-top-queries.sql").read_text(encoding="utf-8")
    assert "statement_start_offset" in text and "statement_end_offset" in text and "total_logical_reads" in text


def test_no_script_hard_codes_a_session_id():
    for f in SQL_FILES:
        body = "\n".join(l for l in (SQL / f).read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
        assert not re.search(r"session_id\s*=\s*\d", body, re.IGNORECASE), f
