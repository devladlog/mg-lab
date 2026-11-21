"""The local check (DuckDB model of the drill) and the CLI around it."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ha_lab as lab  # noqa: E402


def test_local_model_matches_expected(capsys):
    assert lab.run_local() == 0
    out = capsys.readouterr().out
    assert "local checks: the order counts of the drill match expected/" in out
    import re
    assert re.search(r"Orders on the promoted copy\s+13", out)


def test_local_model_notices_a_wrong_expected_file(monkeypatch, tmp_path, capsys):
    (tmp_path).mkdir(exist_ok=True)
    for f in (ROOT / "expected").glob("*.csv"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "h07-repair-chain.csv").write_text("Item,Result\nOrders on the primary,11\nOrders on the standby,10\n"
                                                    "Log backups restored on the standby,3\n", encoding="utf-8")
    monkeypatch.setattr(lab, "EXPECTED_DIR", tmp_path)
    assert lab.run_local() == 1
    assert "local checks FAILED" in capsys.readouterr().out


def test_diff_wild_star_matches_anything_including_null():
    exp = [["A", "B"], ["x", "*"], ["y", "*"]]
    assert lab.diff_wild(exp, [["A", "B"], ["x", "2026-11-21 10:00:00"], ["y", "NULL"]]) == []
    assert lab.diff_wild(exp, [["A", "B"], ["z", "1"], ["y", "1"]])
    assert lab.diff_wild(exp, [["A", "C"], ["x", "1"], ["y", "1"]])[0].startswith("columns")
    assert "rows" in lab.diff_wild(exp, [["A", "B"], ["x", "1"]])[0]


def test_cli_requires_connection_string(monkeypatch):
    monkeypatch.delenv("SQL_CONNECTION_STRING", raising=False)
    with pytest.raises(SystemExit):
        lab.main(["--engine", "sqlserver"])


def test_cli_rejects_unknown_step():
    with pytest.raises(SystemExit):
        lab.main(["--step", "h99-nothing"])


def test_every_step_has_a_sql_file_and_an_expected_file():
    for s in lab.STEPS:
        assert (lab.SQL_DIR / f"{s.sql or s.key}.sql").exists(), s.key
        assert (lab.EXPECTED_DIR / f"{s.key}.csv").exists(), s.key
    assert len({s.key for s in lab.STEPS}) == len(lab.STEPS) == 10
