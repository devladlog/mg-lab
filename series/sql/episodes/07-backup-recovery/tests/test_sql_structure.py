"""Every script parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar), plus the claims the
episode makes: every backup has CHECKSUM, the restore chain is NORECOVERY ... then one RECOVERY, every RESTORE
carries the same STOPAT, no hard-coded paths, the accident comes after the mark and before the last log backup.
The RESTORE statements that b06 builds as text are evaluated here and parsed too, like the planner's."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import backup_lab as lab  # noqa: E402
import restore_plan as rp  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")

SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODE5 = ROOT.parent / "05-stored-procedures-functions"


def statements(name):
    return [st for b in tsqlparse.parse_all_sql()[name]["batches"] for st in b["statements"]]


def all_statements():
    return [(f, st) for f in SQL_FILES for st in statements(f)]


def of_type(*types):
    return [(f, st["text"]) for f, st in all_statements() if st["type"] in types]


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = tsqlparse.parse_all_sql()[name]
    assert f["errors"] == [], f["errors"]
    assert statements(name)


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("RESTORE LOG ContosoBikesRecovered FROM WITH NORECOVERY STOPAT;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


@pytest.mark.skipif(not EPISODE5.exists(), reason="episode 5 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode5():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODE5 / "src" / "sql" / "01-schema-and-data.sql").read_bytes()


@pytest.mark.skipif(not (ROOT.parent / "06-sql-server-security").exists(), reason="episode 6 folder not present")
@pytest.mark.parametrize("rel", ["src/labdb.py", "tools/TsqlParse/Program.cs", "tools/TsqlParse/TsqlParse.csproj"])
def test_shared_code_is_the_same_as_episode6(rel):
    assert (ROOT / rel).read_bytes() == (ROOT.parent / "06-sql-server-security" / rel).read_bytes()


def test_there_are_five_database_backups_and_log_backups_as_planned():
    dbs = of_type("BackupDatabaseStatement")
    logs = of_type("BackupTransactionLogStatement")
    assert [f for f, _ in dbs] == ["b02-full-backup.sql", "b03-differential-backup.sql"]
    assert [f for f, _ in logs] == ["b01-log-before-full.sql", "b04-log-backup.sql", "b05-incident.sql"]
    assert [f for f, t in dbs if "DIFFERENTIAL" in t] == ["b03-differential-backup.sql"]


def test_every_backup_has_checksum_and_overwrites_its_own_file():
    for f, text in of_type("BackupDatabaseStatement", "BackupTransactionLogStatement"):
        assert "CHECKSUM" in text and "INIT" in text, (f, text)
        if f != "b01-log-before-full.sql":
            assert "COMPRESSION" in text, f


def test_backup_file_names_are_the_ones_the_restore_and_the_runner_use():
    restore = (SQL / "b06-restore-copy.sql").read_text(encoding="utf-8")
    backup_names = []
    for f in ("b02-full-backup", "b03-differential-backup", "b04-log-backup", "b05-incident"):
        backup_names += re.findall(r"N'(MGLab_ContosoBikesBackup_\w+\.(?:bak|trn))'", (SQL / f"{f}.sql").read_text(encoding="utf-8"))
    assert backup_names == lab.EXPECTED_FILES
    assert re.findall(r"N'(MGLab_ContosoBikesBackup_\w+\.(?:bak|trn))'", restore) == lab.EXPECTED_FILES


def test_no_hard_coded_folders_or_credentials():
    for f in SQL_FILES:
        text = (SQL / f).read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\", text), f
        assert "InstanceDefaultBackupPath" in text or not f.startswith(("b01", "b02", "b03", "b04", "b05", "b06", "b07")), f
        assert not re.search(r"PASSWORD|PWD=", text, re.IGNORECASE), f


def evaluate_b06() -> list[str]:
    """The five statements b06 inserts into @chain, evaluated like T-SQL: CONCAT of N'...' literals and variables."""
    text = (SQL / "b06-restore-copy.sql").read_text(encoding="utf-8")
    block = text.split("INSERT INTO @chain (Seq, Stmt) VALUES", 1)[1].split(";\nDECLARE @seq", 1)[0]
    variables = {"q": "'", "bak": "C:\\SQL\\Backup\\", "mdf": "'C:\\SQL\\Data\\x.mdf'", "ldf": "'C:\\SQL\\Log\\x.ldf'",
                 "stopText": "'2026-11-21T10:02:45.120'"}
    out = []
    for m in re.finditer(r"\((\d), (CONCAT\(.*?\)|N'[^']*(?:''[^']*)*')\)(?:,|$)", block, re.DOTALL):
        body = m.group(2)
        if body.startswith("CONCAT("):
            body = body[len("CONCAT("):-1]
        pieces = re.findall(r"N'(?:[^']|'')*'|@\w+", body)
        assert "".join(pieces) .replace(" ", "") != "", m.group(1)
        out.append("".join(variables[p[1:]] if p.startswith("@") else p[2:-1].replace("''", "'") for p in pieces))
    return out


def test_b06_builds_the_restore_chain_in_order():
    stmts = evaluate_b06()
    assert len(stmts) == 5
    kinds = [s.split(" FROM")[0].split(" WITH")[0] for s in stmts]
    assert kinds == ["RESTORE DATABASE ContosoBikesRecovered", "RESTORE DATABASE ContosoBikesRecovered",
                     "RESTORE LOG ContosoBikesRecovered", "RESTORE LOG ContosoBikesRecovered",
                     "RESTORE DATABASE ContosoBikesRecovered"]
    for s in stmts[:-1]:
        assert "NORECOVERY" in s and "CHECKSUM" in s and "STOPAT = '2026-11-21T10:02:45.120'" in s, s
    assert stmts[-1] == "RESTORE DATABASE ContosoBikesRecovered WITH RECOVERY;"
    assert stmts[0].count("MOVE") == 2 and all("MOVE" not in s for s in stmts[1:])
    assert [re.search(r"MGLab_ContosoBikesBackup_(\w+)\.", s).group(1) for s in stmts[:-1]] == ["Full", "Diff", "Log1", "Log2"]


def test_the_restore_statements_b06_builds_parse_with_scriptdom(tmp_path):
    script = tmp_path / "chain.sql"
    script.write_text("\n".join(evaluate_b06()) + "\n", encoding="utf-8")
    code, files = tsqlparse.parse(script)
    assert code == 0 and files[0]["errors"] == []
    types = [st["type"] for b in files[0]["batches"] for st in b["statements"]]
    assert types == ["RestoreStatement"] * 5


def test_b06_reads_the_target_from_the_mark_and_restores_into_the_copy_only():
    text = (SQL / "b06-restore-copy.sql").read_text(encoding="utf-8")
    assert "FROM ContosoBikesBackup.dbo.RecoveryMarks WHERE Name = N'before-bad-update'" in text
    assert re.findall(r"RESTORE (?:DATABASE|LOG) (\w+)", text) == ["ContosoBikesRecovered"] * 5
    assert "ContosoBikesBackup_log" in text                      # logical names of a database created with defaults


def test_the_planner_output_parses_with_scriptdom(tmp_path):
    t = datetime(2026, 11, 21, 10, 2, 45, 120000)
    rows = [rp.BackupRow(k, t - timedelta(minutes=m), t - timedelta(minutes=m - 1), Decimal(a), Decimal(b), False, f"C:\\b\\{n}")
            for k, m, a, b, n in (("D", 9, 100, 200, "f.bak"), ("I", 6, 100, 300, "d.bak"), ("L", 3, 200, 400, "l1.trn"),
                                  ("L", -1, 400, 600, "l2.trn"))]
    stmts = rp.render(rp.build_plan(rows, t), "ContosoBikesRecovered",
                      {"ContosoBikesBackup": "C:\\d\\x.mdf", "ContosoBikesBackup_log": "C:\\l\\x.ldf"})
    script = tmp_path / "plan.sql"
    script.write_text("\n".join(stmts) + "\n", encoding="utf-8")
    code, files = tsqlparse.parse(script)
    assert code == 0 and files[0]["errors"] == [] and len(stmts) == 5


def test_b01_is_a_log_backup_before_any_full_backup():
    order = [(f, st["type"]) for f, st in all_statements() if f in ("b01-log-before-full.sql", "b02-full-backup.sql")
             and st["type"].startswith("Backup")]
    assert order == [("b01-log-before-full.sql", "BackupTransactionLogStatement"), ("b02-full-backup.sql", "BackupDatabaseStatement")]
    assert lab.STEPS[0].key == "b01-log-before-full" and lab.STEPS[1].key == "b02-full-backup"


def test_incident_order_mark_then_update_then_order_then_log_backup():
    types = [(st["type"], st["line"]) for st in statements("b05-incident.sql")]
    names = [t for t, _ in types]
    mark = next(i for i, st in enumerate(statements("b05-incident.sql")) if "RecoveryMarks (Name, MarkTime)" in st["text"])
    update = next(i for i, st in enumerate(statements("b05-incident.sql")) if st["type"] == "UpdateStatement")
    new_order = next(i for i, st in enumerate(statements("b05-incident.sql")) if "VALUES\n    (1012" in st["text"])
    log = names.index("BackupTransactionLogStatement")
    assert mark < update < new_order < log
    bad = statements("b05-incident.sql")[update]["text"]
    assert bad == "UPDATE Sales.Products SET ListPrice = 0;" and "WHERE" not in bad


def test_mark_is_stored_as_datetime_because_stopat_takes_datetime():
    assert "MarkTime datetime     NOT NULL" in (SQL / "b05-incident.sql").read_text(encoding="utf-8")


def test_verify_and_check_steps():
    texts = {f: st["text"] for f, st in all_statements() if f == "b07-verify-and-repair.sql"}
    types = [st["type"] for st in statements("b07-verify-and-repair.sql")]
    assert "DbccStatement" in types and "RestoreStatement" in types
    restore = next(st["text"] for st in statements("b07-verify-and-repair.sql") if st["type"] == "RestoreStatement")
    assert "VERIFYONLY" in restore and "WITH CHECKSUM" in restore
    dbcc = next(st["text"] for st in statements("b07-verify-and-repair.sql") if st["type"] == "DbccStatement")
    assert "CHECKDB" in dbcc and "ContosoBikesRecovered" in dbcc and "ContosoBikesBackup" not in dbcc.replace("ContosoBikesRecovered", "")


def test_the_repair_never_overwrites_the_live_database():
    for f in SQL_FILES:
        text = (SQL / f).read_text(encoding="utf-8")
        assert not re.search(r"RESTORE (DATABASE|LOG)\s+ContosoBikesBackup\b", text), f
        assert not re.search(r"REPLACE\b", text.replace("REPLACE(", "")), f


def test_reset_drops_both_databases_and_their_history():
    text = (SQL / "b00-reset.sql").read_text(encoding="utf-8")
    assert "DROP DATABASE IF EXISTS ContosoBikesBackup;" in text and "DROP DATABASE IF EXISTS ContosoBikesRecovered;" in text
    assert text.count("sp_delete_database_backuphistory") == 2


def test_database_is_created_in_full_recovery():
    assert "SET RECOVERY FULL" in (SQL / "00-create-database.sql").read_text(encoding="utf-8")


def test_data_files_are_portable_inserts():
    for f in ("d01-orders-after-full.sql", "d02-order-after-diff.sql"):
        assert {st["type"] for st in statements(f)} == {"InsertStatement"}
