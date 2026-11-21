"""Every script parsed with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar), plus the claims the episode makes:
the group is synchronous commit with automatic failover and automatic seeding, the secondary starts unreadable (the gotcha),
the endpoints mirror each other, the reset drops the group before the database, no hard-coded folders.

ScriptDom's grammar does not know four things that Learn documents for ALTER/CREATE AVAILABILITY GROUP: the WITH options
CLUSTER_TYPE and DB_FAILOVER, SEEDING_MODE = AUTOMATIC, GRANT CREATE ANY DATABASE, and ADD LISTENER. Exactly those pieces (GAPS
below, matched by pattern and counted) are cut out; the REST of each file is parsed by ScriptDom. Only a real run proves the lines
themselves, and demo.md says so."""
from __future__ import annotations

import atexit
import re
import shutil
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest

import tsqlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ag_health  # noqa: E402
import ag_lab as lab  # noqa: E402

pytestmark = pytest.mark.skipif(not tsqlparse.available(), reason=".NET SDK not installed (needed for ScriptDom)")

SQL = ROOT / "src" / "sql"
SQL_FILES = sorted(p.name for p in SQL.glob("*.sql"))
EPISODES = ROOT.parent
TMP = Path(tempfile.mkdtemp(prefix="ag-gaps-"))
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

# text (regex) that ScriptDom can't parse, and how often it occurs -> removed before parsing. Learn documents all of it.
GAPS = {
    "a05-create-ag.sql": [(r"WITH \(CLUSTER_TYPE = WSFC, DB_FAILOVER = ON\)\n", 1), (r"SEEDING_MODE = AUTOMATIC, ", 2)],
    "a06-join-ag.sql": [(r"ALTER AVAILABILITY GROUP ag_contoso GRANT CREATE ANY DATABASE;\n", 1)],
    "a15-listener.sql": [(r"ALTER AVAILABILITY GROUP ag_contoso ADD LISTENER '[\w-]+' "
                          r"\(WITH IP \(\(N'\d+\.\d+\.\d+\.\d+', N'\d+\.\d+\.\d+\.\d+'\)\), PORT = \d+\);\n", 1)],
}


def text(name):
    return (SQL / name).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def parsed(name):
    """ScriptDom's view of the file; for the files in GAPS, of the file without its documented-but-unknown parts."""
    if name not in GAPS:
        return tsqlparse.parse_all_sql()[name]
    body = text(name)
    for pattern, count in GAPS[name]:
        body, n = re.subn(pattern, "", body)
        assert n == count, (name, pattern, n)
    out = TMP / name
    out.write_text(body, encoding="utf-8")
    code, files = tsqlparse.parse(out)
    return files[0]


def statements(name):
    return [st for b in parsed(name)["batches"] for st in b["statements"]]


def of_type(*types):
    return [(f, st["text"]) for f in SQL_FILES for st in statements(f) if st["type"] in types]


@pytest.mark.parametrize("name", SQL_FILES)
def test_every_file_parses_with_scriptdom(name):
    f = parsed(name)
    assert f["errors"] == [], f["errors"]
    assert statements(name)


def test_the_parser_really_rejects_bad_tsql(tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text("ALTER AVAILABILITY GROUP FAILOVER ag_contoso;\n", encoding="utf-8")
    code, files = tsqlparse.parse(bad)
    assert code == 1 and files[0]["errors"]


def test_the_gap_lines_are_the_only_things_scriptdom_cannot_read():
    for name in GAPS:
        code, files = tsqlparse.parse(SQL / name)
        assert files[0]["errors"], f"{name}: ScriptDom now parses the whole file: drop it from GAPS"


@pytest.mark.skipif(not (EPISODES / "05-stored-procedures-functions").exists(), reason="episode 5 folder not present")
def test_schema_file_is_an_unchanged_copy_of_episode5():
    assert (SQL / "01-schema-and-data.sql").read_bytes() == (EPISODES / "05-stored-procedures-functions/src/sql/01-schema-and-data.sql").read_bytes()


@pytest.mark.skipif(not (EPISODES / "08-sql-server-performance-tuning").exists(), reason="episode 8 folder not present")
@pytest.mark.parametrize("rel", ["src/labdb.py", "tools/TsqlParse/Program.cs", "tools/TsqlParse/TsqlParse.csproj", "tests/tsqlparse.py"])
def test_shared_code_is_the_same_as_episode8(rel):
    assert (ROOT / rel).read_bytes() == (EPISODES / "08-sql-server-performance-tuning" / rel).read_bytes()


def test_create_group_is_synchronous_automatic_seeded_and_unreadable_at_first():
    st = statements("a05-create-ag.sql")
    create = [s for s in st if s["type"] == "CreateAvailabilityGroupStatement"]
    assert len(create) == 1
    t = create[0]["text"]
    assert "FOR DATABASE ContosoBikesAG" in t and t.count("AVAILABILITY_MODE = SYNCHRONOUS_COMMIT") == 2
    assert t.count("FAILOVER_MODE = AUTOMATIC") == 2
    assert t.count("SECONDARY_ROLE (ALLOW_CONNECTIONS = NO)") == 2
    assert re.findall(r"REPLICA ON\s+'(CON-SQL0\d)'|^\s+'(CON-SQL0\d)' WITH", text("a05-create-ag.sql"), re.M)
    assert re.findall(r"ENDPOINT_URL = 'TCP://(CON-SQL0\d)\.lab\.contoso\.com:5022'", t) == ["CON-SQL01", "CON-SQL02"]
    assert "CLUSTER_TYPE = WSFC" in text("a05-create-ag.sql") and "DB_FAILOVER = ON" in text("a05-create-ag.sql")
    code = "\n".join(l for l in text("a05-create-ag.sql").splitlines() if not l.lstrip().startswith("--"))
    assert code.count("SEEDING_MODE = AUTOMATIC") == 2


def test_replica_names_match_the_lab_machines():
    names = re.findall(r"^\s+'(CON-SQL0\d)' WITH", text("a05-create-ag.sql"), re.M)
    assert names == list(lab.NODES.values())
    modify = re.findall(r"MODIFY REPLICA ON '(CON-SQL0\d)'", text("a09-allow-read.sql"))
    assert modify == names


def test_join_then_grant_create_any_database_on_the_secondary():
    t = text("a06-join-ag.sql")
    assert [s["type"] for s in statements("a06-join-ag.sql")][1:] == ["AlterAvailabilityGroupStatement"]
    assert t.index("JOIN;") < t.index("GRANT CREATE ANY DATABASE;")


def test_allow_read_modifies_both_replicas_to_all():
    st = [s["text"] for s in statements("a09-allow-read.sql") if s["type"] == "AlterAvailabilityGroupStatement"]
    assert len(st) == 2 and all("SECONDARY_ROLE (ALLOW_CONNECTIONS = ALL)" in s for s in st)


def test_the_planned_failover_is_one_statement():
    st = [s["text"] for s in statements("a12-failover.sql") if s["type"] == "AlterAvailabilityGroupStatement"]
    assert st == ["ALTER AVAILABILITY GROUP ag_contoso FAILOVER;"]


def test_the_failure_a08_reads_the_secondary_without_using_the_database():
    st = [s for s in statements("a08-secondary-read-fails.sql") if s["type"] == "SelectStatement"]
    assert len(st) == 1 and "FROM ContosoBikesAG.Sales.Orders" in st[0]["text"]
    assert not any(s["type"] == "UseStatement" and "ContosoBikesAG" in s["text"] for s in statements("a08-secondary-read-fails.sql"))


def test_endpoint_scripts_mirror_each_other():
    a, b = text("a03-endpoint-sql01.sql"), text("a03-endpoint-sql02.sql")
    for t in (a, b):
        assert "CREATE ENDPOINT Hadr_endpoint" in t and "LISTENER_PORT = 5022" in t
        assert "ROLE = ALL, AUTHENTICATION = WINDOWS NEGOTIATE, ENCRYPTION = REQUIRED ALGORITHM AES" in t
        assert "IF NOT EXISTS (SELECT 1 FROM sys.database_mirroring_endpoints WHERE name = N'Hadr_endpoint')" in t
    assert set(re.findall(r"CONTOSO\\(CON-SQL0\d)\$", a)) == {"CON-SQL02"}
    assert set(re.findall(r"CONTOSO\\(CON-SQL0\d)\$", b)) == {"CON-SQL01"}
    assert "GRANT CONNECT ON ENDPOINT::Hadr_endpoint TO [CONTOSO\\CON-SQL02$];" in a
    assert "GRANT CONNECT ON ENDPOINT::Hadr_endpoint TO [CONTOSO\\CON-SQL01$];" in b
    assert [s["type"] for s in statements("a03-endpoint-sql01.sql")] == [s["type"] for s in statements("a03-endpoint-sql02.sql")]


def test_endpoint_port_in_the_group_is_the_endpoint_port():
    ports = set(re.findall(r":(\d+)'", text("a05-create-ag.sql")))
    assert ports == {"5022"} and "LISTENER_PORT = 5022" in text("a03-endpoint-sql01.sql")
    assert "5022" in (ROOT / "src/ps/Prepare-AgCluster.ps1").read_text(encoding="utf-8")


def test_teardown_files_drop_what_the_endpoint_files_create():
    for n, peer in (("01", "CON-SQL02"), ("02", "CON-SQL01")):
        t = text(f"a14-teardown-sql{n}.sql")
        assert "DROP ENDPOINT Hadr_endpoint;" in t and f"DROP LOGIN [CONTOSO\\{peer}$];" in t
        assert f"CREATE LOGIN [CONTOSO\\{peer}$] FROM WINDOWS;" in text(f"a03-endpoint-sql{n}.sql")


def test_reset_drops_the_group_before_the_database_and_the_history():
    types = [s["type"] for s in statements("a00-reset.sql")]
    t = text("a00-reset.sql")
    assert t.index("DROP AVAILABILITY GROUP ag_contoso;") < t.index("ALTER DATABASE ContosoBikesAG SET SINGLE_USER") < t.index("DROP DATABASE IF EXISTS ContosoBikesAG;")
    assert "sp_delete_database_backuphistory" in t and types.count("DropDatabaseStatement") == 1


def test_database_prerequisites_full_recovery_and_one_real_full_backup():
    assert "SET RECOVERY FULL" in text("a04-create-database.sql")
    t = text("a04-backup.sql")
    backups = [x for x in of_type("BackupDatabaseStatement") if x[0] == "a04-backup.sql"]
    assert len(backups) == 1 and all(k in backups[0][1] for k in ("INIT", "CHECKSUM", "COMPRESSION"))
    assert "InstanceDefaultBackupPath" in t and not re.search(r"\bNUL\b", t.split("BACKUP DATABASE")[1].split("\n")[0])


def test_no_hard_coded_folders_credentials_or_stray_addresses():
    for f in SQL_FILES:
        t = text(f)
        assert not re.search(r"[A-Za-z]:\\", t), f
        assert not re.search(r"PASSWORD|PWD=", t, re.IGNORECASE), f
        for ip in re.findall(r"\b(\d+\.\d+\.\d+\.\d+)\b", t):
            assert ip.startswith("10.50.0.") or ip == "255.255.255.0", (f, ip)


def test_lab_addresses_do_not_collide():
    ips = {"listener": re.search(r"N'(10\.50\.0\.\d+)'", text("a15-listener.sql")).group(1),
           "cluster": re.search(r"\$ClusterIp = '([\d.]+)'", (ROOT / "src/ps/Prepare-AgCluster.ps1").read_text(encoding="utf-8")).group(1)}
    assert len(set(ips.values())) == 2
    assert not set(ips.values()) & {"10.50.0.10", "10.50.0.21", "10.50.0.22", "10.50.0.30", "10.50.0.41", "10.50.0.42"}
    assert all(40 <= int(v.rsplit(".", 1)[1]) <= 99 for v in ips.values())


def test_health_query_columns_are_the_ones_ag_health_reads():
    t = text("a07-health.sql")
    assert re.findall(r"\bAS (\w+)\s*(?:,|\n\s*FROM)", t) == ag_health.COLUMNS
    for view in ("sys.availability_groups", "sys.availability_replicas", "sys.dm_hadr_availability_replica_states",
                 "sys.dm_hadr_database_replica_states"):
        assert view in t
    assert "ORDER BY ar.replica_server_name" in t and "LEFT JOIN sys.dm_hadr_database_replica_states" in t


def test_prereq_query_reads_the_documented_cluster_views_and_counts_only_nodes():
    t = text("a02-prereqs.sql")
    assert "SERVERPROPERTY(N'IsHadrEnabled')" in t and "sys.dm_hadr_cluster" in t and "sys.dm_hadr_cluster_members" in t
    assert "member_type_desc = N'CLUSTER_NODE'" in t and "member_state_desc = N'UP'" in t
    assert re.findall(r"AS (\w+)", t) == ["Node", "HadrEnabled", "Collation", "ProductVersion", "QuorumState", "NodesUp"]


def test_data_files_are_portable_inserts_of_the_orders_they_name():
    for n, f in ((1009, "d01-order-1009.sql"), (1010, "d02-order-1010.sql")):
        assert {st["type"] for st in statements(f)} == {"InsertStatement"}
        assert len(re.findall(rf"\({n}, ", text(f))) == 2, f


def test_every_sql_server_script_is_used_by_a_step():
    used = {a.file + ".sql" for s in lab.STEPS for a in s.actions} | {"a00-reset.sql", "a14-teardown-sql01.sql", "a14-teardown-sql02.sql", "a16-role.sql"}
    assert used == set(SQL_FILES)
