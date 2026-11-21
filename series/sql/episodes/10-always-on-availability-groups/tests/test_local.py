"""The local check (DuckDB model of the data side) and the CLI around it."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ag_lab as lab  # noqa: E402


def test_local_model_matches_expected(capsys):
    assert lab.run_local() == 0
    out = capsys.readouterr().out
    assert "local checks: the order counts of the drill match expected/" in out
    assert re.search(r"Orders on this replica\s+10", out) and "primary sql01 has 10 orders, secondary sql02 has 10" in out


def test_local_model_notices_a_wrong_expected_file(monkeypatch, tmp_path, capsys):
    for f in (ROOT / "expected").glob("*.csv"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "a11-write-and-read.csv").write_text("Item,Result\nOrders on this replica,8\nRole of this replica,SECONDARY\n", encoding="utf-8")
    monkeypatch.setattr(lab, "EXPECTED_DIR", tmp_path)
    assert lab.run_local() == 1
    assert "local checks FAILED" in capsys.readouterr().out


def test_diff_wild():
    exp = [["A", "B"], ["x", "*"]]
    assert lab.diff_wild(exp, [["A", "B"], ["x", "NULL"]]) == []
    assert lab.diff_wild(exp, [["A", "B"], ["y", "1"]])
    assert lab.diff_wild(exp, [["A", "C"], ["x", "1"]])[0].startswith("columns")


def test_cli_requires_both_connection_strings(monkeypatch):
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=fake")
    monkeypatch.delenv("SQL_CONNECTION_STRING_SQL02", raising=False)
    with pytest.raises(SystemExit):
        lab.main(["--engine", "sqlserver"])


def test_cli_rejects_unknown_step():
    with pytest.raises(SystemExit):
        lab.main(["--step", "a99-nothing"])


def test_every_step_has_files_and_an_expected_csv():
    keys = [s.key for s in lab.STEPS]
    assert len(set(keys)) == len(keys) == 11 and sum(s.optional for s in lab.STEPS) == 1
    for s in lab.STEPS:
        for a in s.actions:
            assert (lab.SQL_DIR / f"{a.file}.sql").exists(), (s.key, a.file)
            assert a.node in lab.NODES
        if s.result:
            assert (lab.EXPECTED_DIR / f"{s.expected or s.key}.csv").exists(), s.key


def test_the_optional_listener_only_runs_when_asked_for(monkeypatch):
    seen = {}
    monkeypatch.setenv("SQL_CONNECTION_STRING", "Server=a")
    monkeypatch.setenv("SQL_CONNECTION_STRING_SQL02", "Server=b")
    monkeypatch.setattr(lab, "run_sqlserver", lambda connect, steps, setup: seen.update(keys=[s.key for s in steps]) or 0)
    lab.main(["--engine", "sqlserver"])
    assert "a15-listener" not in seen["keys"] and len(seen["keys"]) == 10
    lab.main(["--engine", "sqlserver", "--step", "a15-listener"])
    assert seen["keys"] == ["a15-listener"]
