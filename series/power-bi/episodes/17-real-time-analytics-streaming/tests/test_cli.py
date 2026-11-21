import json

import cli
import reference


def test_dry_run_then_expect(tmp_path, capsys):
    f = tmp_path / "run.ndjson"
    assert cli.main(["send", "--dry-run", str(f), "--no-wait", "--minutes", "4", "--rate", "20"]) == 0
    out = capsys.readouterr().out
    assert "unique EventId" in out and "amount (unique)" in out
    rows = reference.read_ndjson(f)
    assert all(json.loads(json.dumps(r)) == r for r in rows) and len(rows) >= 40
    assert cli.main(["expect", str(f)]) == 0
    assert "raw_rows=" in capsys.readouterr().out


def test_send_without_a_connection_string_explains_itself(monkeypatch, capsys):
    monkeypatch.delenv("TILLSTREAM_CONNECTION_STRING", raising=False)
    assert cli.main(["send"]) == 2
    assert "TILLSTREAM_CONNECTION_STRING" in capsys.readouterr().err


def test_a_connection_string_without_entity_path_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("TILLSTREAM_CONNECTION_STRING", "Endpoint=sb://x.servicebus.windows.net/;SharedAccessKeyName=k;SharedAccessKey=v")
    assert cli.main(["send"]) == 2
    assert "EntityPath" in capsys.readouterr().err


def test_push_and_inventory_need_a_token(monkeypatch, capsys):
    monkeypatch.delenv("PBI_ACCESS_TOKEN", raising=False)
    assert cli.main(["push", "--workspace-id", "00000000-0000-0000-0000-000000000000"]) == 2
    assert cli.main(["inventory"]) == 2
    assert capsys.readouterr().err.count("PBI_ACCESS_TOKEN") == 2


def test_secrets_are_not_command_line_arguments():
    """The connection string and the token come from environment variables only (a command line is visible in the process list and in history)."""
    text = open(cli.__file__, encoding="utf-8").read()
    assert "--token" not in text and "--connection-string" not in text and "--key" not in text
