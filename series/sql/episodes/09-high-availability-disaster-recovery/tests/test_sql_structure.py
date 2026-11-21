"""Every script parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar), plus the claims the episode
makes: every backup has CHECKSUM and INIT, every standby restore is WITH STANDBY with an undo file, the failover is a
tail-log backup WITH NORECOVERY followed by a restore WITH RECOVERY, the data files are the orders they say, no
hard-coded folders. The RESTORE that h02 builds as text is evaluated here and parsed too."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ha_lab as lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")

SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODES = ROOT.parent


def statements(name):
    return [st for b in tsqlparse.parse_all_sql()[name]["batches"] for st in b["statements"]]


def all_statements():
    return [(f, st) for f in SQL_FILES for st in statements(f)]


def of_type(*types):
    return [(f, st["text"]) for f, st in all_statements() if st["type"] in types]


def text(name):
    return (SQL / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert statements(name)


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("RESTORE LOG ContosoBikesHA_Standby FROM WITH STANDBY;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not (EPISODES / "05-stored-procedures-functions").exists(), reason="episode 5 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode5():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODES / "05-stored-procedures-functions/src/sql/01-schema-and-data.sql").read_bytes()


@pytest.mark.skipif(not (EPISODES / "08-sql-server-performance-tuning").exists(), reason="episode 8 folder not present")
@pytest.mark.parametrize("rel", ["src/labdb.py", "tools/TsqlParse/Program.cs", "tools/TsqlParse/TsqlParse.csproj", "tests/tsqlparse.py"])
def test_shared_code_is_the_same_as_episode8(rel):
    assert (ROOT / rel).read_bytes() == (EPISODES / "08-sql-server-performance-tuning" / rel).read_bytes()


def test_statement_inventory():
    dbs = [f for f, _ in of_type("BackupDatabaseStatement")]
    logs = [f for f, _ in of_type("BackupTransactionLogStatement")]
    assert dbs == ["h02-init-standby.sql"]
    assert logs == ["h03-ship-log.sql", "h05-rogue-log-backup.sql", "h06-ship-log-fails.sql", "h08-failover.sql"]


def test_every_backup_has_checksum_init_and_compression():
    for f, t in of_type("BackupDatabaseStatement", "BackupTransactionLogStatement"):
        assert "CHECKSUM" in t and "INIT" in t and "COMPRESSION" in t, (f, t)


def test_every_restore_has_checksum():
    for f, t in of_type("RestoreStatement"):
        assert "CHECKSUM" in t, (f, t)


def test_every_restore_on_the_standby_before_the_failover_is_with_standby_and_an_undo_file():
    for f in ("h03-ship-log.sql", "h06-ship-log-fails.sql", "h07-repair-chain.sql"):
        restores = [t for ff, t in of_type("RestoreStatement") if ff == f]
        assert restores and all("RESTORE LOG ContosoBikesHA_Standby" in t and "STANDBY = @undo" in t for t in restores), f
        assert all("RECOVERY" not in t for t in restores), f
    assert "MGLab_ContosoBikesHA_Standby.undo" in text("h03-ship-log.sql")


def test_the_repair_restores_the_missing_log_before_the_one_that_failed():
    restores = [t for f, t in of_type("RestoreStatement") if f == "h07-repair-chain.sql"]
    assert [re.search(r"FROM DISK = (@\w+)", t).group(1) for t in restores] == ["@rogue", "@next"]
    t = text("h07-repair-chain.sql")
    assert "@rogue nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Rogue.trn'" in t
    assert "@next nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Log2.trn'" in t


def test_the_failover_is_a_tail_log_backup_then_restore_with_recovery():
    f = [(ff, t) for ff, t in of_type("BackupTransactionLogStatement", "RestoreStatement") if ff == "h08-failover.sql"]
    assert [t.split()[0] + " " + t.split()[1] for _, t in f] == ["BACKUP LOG", "RESTORE LOG"]
    assert "WITH NORECOVERY" in f[0][1] and "ContosoBikesHA " in f[0][1]
    assert "WITH RECOVERY" in f[1][1] and "ContosoBikesHA_Standby" in f[1][1] and "STANDBY" not in f[1][1]


def test_the_failover_never_touches_the_standby_before_the_tail_is_taken():
    types = [(st["type"]) for st in statements("h08-failover.sql")]
    assert types.index("BackupTransactionLogStatement") < types.index("RestoreStatement")


def test_backup_file_names_match_the_runner():
    names = []
    for f in ("h02-init-standby", "h03-ship-log", "h05-rogue-log-backup", "h06-ship-log-fails", "h08-failover"):
        names += re.findall(r"N'(MGLab_ContosoBikesHA_(?:Full|Log1|Rogue|Log2|Tail)\.(?:bak|trn))'", text(f + ".sql"))
    assert names == lab.EXPECTED_FILES
    assert re.findall(r"N'(MGLab_ContosoBikesHA_\w+\.(?:bak|trn))'", text("h07-repair-chain.sql")) == [
        "MGLab_ContosoBikesHA_Rogue.trn", "MGLab_ContosoBikesHA_Log2.trn"]


def test_no_hard_coded_folders_or_credentials():
    for f in SQL_FILES:
        t = text(f)
        assert not re.search(r"[A-Za-z]:\\", t), f
        assert not re.search(r"PASSWORD|PWD=", t, re.IGNORECASE), f
        if re.search(r"\bBACKUP (DATABASE|LOG)|\bRESTORE LOG", t):
            assert "InstanceDefaultBackupPath" in t, f


def evaluate_h02() -> str:
    """The RESTORE that h02 builds with CONCAT, evaluated like T-SQL (N'...' literals and variables)."""
    t = text("h02-init-standby.sql")
    block = t.split("DECLARE @sql nvarchar(max) = CONCAT(", 1)[1].split(");\nEXEC", 1)[0]
    variables = {"q": "'", "full": "C:\\SQL\\Backup\\MGLab_ContosoBikesHA_Full.bak",
                 "mdf": "'C:\\SQL\\Data\\MGLab_ContosoBikesHA_Standby.mdf'",
                 "ldf": "'C:\\SQL\\Log\\MGLab_ContosoBikesHA_Standby_log.ldf'",
                 "undo": "'C:\\SQL\\Data\\MGLab_ContosoBikesHA_Standby.undo'"}
    pieces = re.findall(r"N'(?:[^']|'')*'|@\w+", block)
    return "".join(variables[p[1:]] if p.startswith("@") else p[2:-1].replace("''", "'") for p in pieces)


def test_h02_builds_a_standby_restore_with_move():
    s = evaluate_h02()
    assert s.startswith("RESTORE DATABASE ContosoBikesHA_Standby FROM DISK = 'C:\\SQL\\Backup\\MGLab_ContosoBikesHA_Full.bak'")
    assert s.count("MOVE") == 2 and "STANDBY = 'C:\\SQL\\Data\\MGLab_ContosoBikesHA_Standby.undo'" in s and "CHECKSUM" in s
    assert "NORECOVERY" not in s and "WITH RECOVERY" not in s


def test_the_restore_h02_builds_parses_with_scriptdom(tmp_path):
    script = tmp_path / "standby.sql"
    script.write_text(evaluate_h02() + "\n", encoding="utf-8")
    code, files = tsqlparse.parse(script)
    assert code == 0 and files[0]["errors"] == []
    assert [st["type"] for b in files[0]["batches"] for st in b["statements"]] == ["RestoreStatement"]


def test_standby_files_never_reuse_the_primary_files():
    t = text("h02-init-standby.sql")
    assert "MGLab_ContosoBikesHA_Standby.mdf" in t and "MGLab_ContosoBikesHA_Standby_log.ldf" in t
    for f in SQL_FILES:
        assert not re.search(r"RESTORE (DATABASE|LOG)\s+ContosoBikesHA\b(?!_)", text(f)), f
        assert not re.search(r"REPLACE\b", text(f).replace("REPLACE(", "")), f


def test_data_files_are_portable_inserts_of_the_orders_they_name():
    for n, f in ((1009, "d01-order-1009.sql"), (1010, "d02-order-1010.sql"), (1011, "d03-order-1011.sql"), (1012, "d04-order-1012.sql")):
        assert {st["type"] for st in statements(f)} == {"InsertStatement"}
        assert len(re.findall(rf"\({n}, ", text(f))) == 2, f


def test_orders_follow_the_shipping_story():
    steps = [s.key for s in lab.STEPS]
    assert steps.index("h03-ship-log") < steps.index("h05-rogue-log-backup") < steps.index("h06-ship-log-fails") \
        < steps.index("h07-repair-chain") < steps.index("h08-failover") < steps.index("h09-write-on-promoted")
    before = {s.key: s.before for s in lab.STEPS}
    assert before["h03-ship-log"] == ["d01-order-1009.sql"] and before["h05-rogue-log-backup"] == ["d02-order-1010.sql"]
    assert before["h06-ship-log-fails"] == ["d03-order-1011.sql"] and before["h08-failover"] == ["d04-order-1012.sql"]


def test_the_standby_write_is_a_plain_insert_into_the_standby():
    st = [x for x in statements("h04-standby-write.sql") if x["type"] == "InsertStatement"]
    assert len(st) == 1 and "ContosoBikesHA_Standby.Sales.Orders" in st[0]["text"]


def test_rpo_query_reads_backupset_for_the_three_backup_types_and_ignores_system_databases():
    t = text("h01-rpo-exposure.sql")
    assert "msdb.dbo.backupset" in t and "bs.type = 'D'" in t and "bs.type = 'I'" in t and "bs.type = 'L'" in t
    assert "d.database_id > 4" in t and "GREATEST(" in t and "<> N'SIMPLE'" in t
    for column in lab.dr_report.COLUMNS:       # the report's columns are the query's aliases, in order
        assert re.search(rf"\b(AS {column}|b\.{column})\b", t), column
    assert [t.index(c) for c in lab.dr_report.COLUMNS[4:7]] == sorted(t.index(c) for c in lab.dr_report.COLUMNS[4:7])


def test_reset_drops_both_databases_and_their_history():
    t = text("h00-reset.sql")
    assert "DROP DATABASE IF EXISTS ContosoBikesHA;" in t and "DROP DATABASE IF EXISTS ContosoBikesHA_Standby;" in t
    assert t.count("sp_delete_database_backuphistory") == 2


def test_primary_is_created_in_full_recovery():
    assert "SET RECOVERY FULL" in text("00-create-database.sql")
