import json

import pandas as pd
import pytest

from slabreach import cli, data, gate, prepare
from slabreach.schema import RAW_COLUMNS, RAW_FILE


def test_generator_is_deterministic_and_has_the_contract():
    a, b = data.generate(800, 3), data.generate(800, 3)
    assert a.equals(b) and list(a.columns) == RAW_COLUMNS
    assert not a.equals(data.generate(800, 4))
    assert set(a.breached) == {0, 1} and a.created_at.is_monotonic_increasing


def test_noisy_scenario_changes_labels_and_missing_column_scenario_drops_one():
    base, noisy = data.generate(2000, 1), data.generate(2000, 1, "noisy")
    assert (base.breached != noisy.breached).mean() > 0.10
    assert "channel" not in data.generate(600, 1, "missing-column").columns
    with pytest.raises(ValueError):
        data.generate(10, 1, "nope")


def test_validate_accepts_good_data_and_lists_every_problem():
    assert prepare.validate(data.generate(1000, 1)) == []
    bad = data.generate(1000, 1)
    bad.loc[0, "priority"] = "P9"
    bad.loc[1, "text_length"] = -5
    bad.loc[2, "created_at"] = "yesterday"
    bad.loc[3, "category"] = None
    errs = prepare.validate(bad)
    text = " | ".join(errs)
    assert "priority: unexpected values ['P9']" in text and "text_length must be a positive" in text
    assert "not dates" in text and "category: 1 empty values" in text


def test_validate_flags_label_rate_and_too_few_rows():
    df = data.generate(1000, 1)
    df["breached"] = 1
    assert any("breach rate 100.0%" in e for e in prepare.validate(df))
    assert any("need at least 500" in e for e in prepare.validate(data.generate(100, 1)))


def test_prepare_splits_by_time_with_no_overlap(tmp_path):
    cli.main(["generate", "--out", str(tmp_path / "raw"), "--rows", "2000"])
    assert prepare.run(tmp_path / "raw", tmp_path / "tr", tmp_path / "te", 0.25) == 0
    tr, te = pd.read_csv(tmp_path / "tr" / RAW_FILE), pd.read_csv(tmp_path / "te" / RAW_FILE)
    assert len(tr) == 1500 and len(te) == 500
    assert tr.created_at.max() <= te.created_at.min()                    # the test set is NEWER than the training set
    assert not set(tr.ticket_id) & set(te.ticket_id)
    rep = json.loads((tmp_path / "tr" / "data_report.json").read_text())
    assert rep["train_rows"] == 1500 and "test_starts" in rep


def test_prepare_refuses_the_missing_column_extract(tmp_path, capsys):
    cli.main(["generate", "--out", str(tmp_path / "raw"), "--scenario", "missing-column"])
    assert prepare.run(tmp_path / "raw", tmp_path / "tr", tmp_path / "te") == 2
    assert "missing columns: channel" in capsys.readouterr().out
    assert not (tmp_path / "tr").exists()                                 # nothing downstream gets half-checked data


def test_prepare_missing_file(tmp_path):
    assert prepare.run(tmp_path, tmp_path / "a", tmp_path / "b") == 2


# ---- the gate as a pure function -------------------------------------------------------------------------------
M = {"auc": 0.78, "p1_recall": 0.8}


def test_gate_passes_good_metrics_with_or_without_a_production_model():
    assert gate.decide(M).promote and gate.decide(M, 0.77).promote


def test_gate_rejects_below_the_floor():
    d = gate.decide({"auc": 0.65, "p1_recall": 0.9})
    assert not d.promote and "below the floor" in d.reasons[0]


def test_gate_rejects_worse_than_production_but_tolerates_small_noise():
    assert not gate.decide({"auc": 0.74, "p1_recall": 0.9}, 0.78).promote       # -0.04
    assert gate.decide({"auc": 0.765, "p1_recall": 0.9}, 0.78).promote          # -0.015 is inside 0.02


def test_gate_rejects_a_bad_slice_even_when_the_average_is_good():
    d = gate.decide({"auc": 0.85, "p1_recall": 0.4})
    assert not d.promote and "P1 breach recall 0.40" in d.reasons[0]
    assert not gate.decide({"auc": 0.85, "p1_recall": None}).promote


def test_gate_reports_every_reason():
    d = gate.decide({"auc": 0.5, "p1_recall": 0.1}, 0.8)
    assert len(d.reasons) == 3
