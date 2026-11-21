import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from migplan import __main__ as cli
from migplan import drgate, migrate_csv, readiness

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def test_headers_equal_the_microsoft_template():
    assert migrate_csv.headers_for(0) == migrate_csv.template_headers()
    h = migrate_csv.template_headers()
    assert h[0] == "*Server name"
    assert {"*Server name", "*Cores", "*Memory (In MB)", "*OS name"} <= set(h)


def test_extra_disks_follow_the_same_pattern():
    h = migrate_csv.headers_for(8)
    assert "Disk 8 size (In GB)" in h and "Disk 8 write ops (operations per second)" in h
    with pytest.raises(ValueError):
        migrate_csv.headers_for(21)


def test_csv_has_bom_crlf_and_round_trips(cmdb, tmp_path):
    out = tmp_path / "import.csv"
    ready = readiness.importable(cmdb, readiness.check_inventory(cmdb))
    migrate_csv.write(ready, out)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert len(rows) == 13
    sql = next(r for r in rows if r["*Server name"].startswith("sql01"))
    assert sql["*Cores"] == "8" and sql["Number of disks"] == "4" and sql["Disk 4 size (In GB)"] == "256"
    assert sql["IP addresses"] == "10.20.4.10"


def test_every_row_fills_mandatory_columns(cmdb, tmp_path):
    ready = readiness.importable(cmdb, readiness.check_inventory(cmdb))
    rows = list(csv.DictReader(io.StringIO(migrate_csv.render(ready))))
    for r in rows:
        assert r["*Server name"] and r["*Cores"] and r["*Memory (In MB)"] and r["*OS name"]


def item(**over):
    base = {
        "name": "vm1",
        "properties": {
            "friendlyName": "vm1", "replicationHealth": "Normal", "protectionState": "Protected",
            "lastSuccessfulTestFailoverTime": (NOW - timedelta(days=10)).isoformat().replace("+00:00", "Z"),
            "allowedOperations": ["TestFailover", "UnplannedFailover", "PlannedFailover"],
            "providerSpecificDetails": {"instanceType": "A2A", "rpoInSeconds": 40,
                                        "lastRpoCalculatedTime": (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")},
        },
    }
    for k, v in over.items():
        if k in base["properties"]["providerSpecificDetails"]:
            base["properties"]["providerSpecificDetails"][k] = v
        else:
            base["properties"][k] = v
    return base


def test_gate_passes_a_healthy_item():
    checks = drgate.evaluate([item()], NOW)
    assert all(c.passed for c in checks) and len(checks) == 5


@pytest.mark.parametrize("change,failing", [
    ({"replicationHealth": "Critical"}, "replication-health"),
    ({"rpoInSeconds": 1200}, "rpo"),
    ({"lastRpoCalculatedTime": "2026-11-19T00:00:00Z"}, "rpo-fresh"),
    ({"lastSuccessfulTestFailoverTime": None}, "test-failover-recent"),
    ({"lastSuccessfulTestFailoverTime": "2026-01-01T00:00:00Z"}, "test-failover-recent"),
    ({"allowedOperations": ["Disable"]}, "failover-allowed"),
])
def test_gate_fails_each_check(change, failing):
    checks = drgate.evaluate([item(**change)], NOW)
    assert {c.name for c in checks if not c.passed} == {failing}
    assert drgate.verdict(checks) == {"vm1": False}


def test_gate_no_rpo_yet_fails():
    checks = drgate.evaluate([item(rpoInSeconds=None)], NOW)
    assert any(c.name == "rpo" and not c.passed for c in checks)


def test_gate_loads_value_wrapper_and_bare_list(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"value": [item()]}))
    q = tmp_path / "b.json"
    q.write_text(json.dumps([item()]))
    assert drgate.load_items(p) == drgate.load_items(q)


def test_cli_check_exit_code_and_output(cmdb_path, capsys):
    assert cli.main(["check", str(cmdb_path)]) == 1          # legacy01 is a blocker
    out = capsys.readouterr().out
    assert "BLOCKER" in out and "legacy01" in out and "Standard_E16s_v5" in out


def test_cli_plan(cmdb_path, capsys):
    assert cli.main(["plan", str(cmdb_path)]) == 0
    out = capsys.readouterr().out
    assert "foundation" in out and "pilot" in out and "blocked until fixed: legacy01" in out


def test_cli_csv(cmdb_path, tmp_path, capsys):
    out = tmp_path / "x.csv"
    assert cli.main(["csv", str(cmdb_path), "--out", str(out)]) == 0
    assert "13 of 14" in capsys.readouterr().out and out.exists()


def test_cli_gate(tmp_path, capsys):
    p = tmp_path / "items.json"
    fresh = datetime.now(timezone.utc)
    good = item(lastSuccessfulTestFailoverTime=(fresh - timedelta(days=1)).isoformat(),
                lastRpoCalculatedTime=(fresh - timedelta(minutes=1)).isoformat())
    p.write_text(json.dumps({"value": [good]}))
    assert cli.main(["gate", str(p)]) == 0 and "READY" in capsys.readouterr().out
    p.write_text(json.dumps({"value": [item(replicationHealth="Warning")]}))
    assert cli.main(["gate", str(p)]) == 1


def test_cli_gate_empty_is_not_ready(tmp_path):
    p = tmp_path / "e.json"
    p.write_text('{"value": []}')
    assert cli.main(["gate", str(p)]) == 1
