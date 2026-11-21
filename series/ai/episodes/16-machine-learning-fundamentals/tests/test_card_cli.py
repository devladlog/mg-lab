import json

import pytest

from mlbasics import card, cli, data, experiments
from mlbasics.data import GROUP, TARGET

TICKET = {"priority": "P1", "category": "network", "department": "finance", "language": "pt", "hour_opened": 22, "weekday": 6,
          "queue_backlog": 18, "attachments": 0, "text_length": 240, "is_vip": 0}


@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    d = tmp_path_factory.mktemp("m")
    df = data.generate(n=2400, requesters=150)
    res = experiments.train_and_test(df)
    c = card.make_card(df, res)
    mp, cp = card.save(res, c, d)
    return mp, cp, c


def test_card_content(saved):
    _, cp, c = saved
    assert json.loads(cp.read_text()) == c
    assert c["excluded"]["identifier"] == GROUP and "first_response_minutes" in c["excluded"]["not available when the ticket arrives"]
    assert c["data"]["fingerprint"] and c["threshold"]["chosen_on"].startswith("out-of-fold")
    assert c["not_for"] and c["intended_use"]


def test_score_ticket(saved):
    mp, cp, c = saved
    r = card.score_ticket(mp, cp, TICKET)
    assert 0 <= r["risk"] <= 1 and r["threshold"] == c["threshold"]["value"] and r["flag_for_dispatcher"] == (r["risk"] >= r["threshold"])
    calm = card.score_ticket(mp, cp, {**TICKET, "priority": "P4", "category": "access", "hour_opened": 10, "weekday": 2, "queue_backlog": 4, "is_vip": 1})
    assert calm["risk"] < r["risk"]


def test_score_refuses_leaky_and_incomplete_tickets(saved):
    mp, cp, _ = saved
    with pytest.raises(card.ScoreError, match="not known when the ticket arrives"):
        card.score_ticket(mp, cp, {**TICKET, "first_response_minutes": 5})
    with pytest.raises(card.ScoreError, match="missing"):
        card.score_ticket(mp, cp, {k: v for k, v in TICKET.items() if k != "priority"})


def test_score_accepts_an_unseen_category(saved):
    mp, cp, _ = saved
    assert 0 <= card.score_ticket(mp, cp, {**TICKET, "department": "marketing"})["risk"] <= 1


def test_cli_data_audit_baseline(tmp_path, capsys):
    out = tmp_path / "t.csv"
    assert cli.main(["data", "--rows", "800", "--out", str(out)]) == 0 and out.exists()
    assert "fingerprint" in capsys.readouterr().out
    assert cli.main(["audit", "--csv", str(out)]) == 1                        # the leaky column is suspect
    assert "SUSPECT" in capsys.readouterr().out
    assert cli.main(["audit", "--csv", str(out), "--drop", "first_response_minutes"]) == 0
    capsys.readouterr()
    assert cli.main(["baseline", "--rows", "1600"]) == 0
    assert "no skill" in capsys.readouterr().out


def test_cli_compare_and_depth(capsys):
    assert cli.main(["compare", "--rows", "1600"]) == 0
    out = capsys.readouterr().out
    assert "random + leaky column" in out and "time split" in out
    assert cli.main(["depth", "--rows", "1600"]) == 0
    assert "best validation" in capsys.readouterr().out


def test_cli_train_exit_codes_and_score(tmp_path, capsys):
    assert cli.main(["train", "--rows", "2400", "--out", str(tmp_path), "--min-lift", "1.0"]) == 0
    assert "ship candidate" in capsys.readouterr().out
    t = tmp_path / "ticket.json"
    t.write_text(json.dumps(TICKET))
    assert cli.main(["score", str(t), "--model", str(tmp_path / "model.joblib"), "--card", str(tmp_path / "model_card.json")]) == 0
    assert "threshold" in capsys.readouterr().out
    assert cli.main(["train", "--rows", "2400", "--out", str(tmp_path), "--min-lift", "100"]) == 1
    assert "do not ship" in capsys.readouterr().out


def test_cli_errors_are_exit_2(tmp_path, capsys):
    assert cli.main(["score", str(tmp_path / "nope.json")]) == 2
    assert "error" in capsys.readouterr().err
    t = tmp_path / "bad.json"
    t.write_text(json.dumps({**TICKET, "first_response_minutes": 3}))
    assert cli.main(["train", "--rows", "1600", "--out", str(tmp_path)]) in (0, 1)
    capsys.readouterr()
    assert cli.main(["score", str(t), "--model", str(tmp_path / "model.joblib"), "--card", str(tmp_path / "model_card.json")]) == 2


def test_target_column_name_is_stable():
    assert TARGET == "breached_sla"
