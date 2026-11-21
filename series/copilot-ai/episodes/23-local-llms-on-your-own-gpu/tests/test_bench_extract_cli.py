import json
from pathlib import Path

import pytest

from local_llm import bench, cli, extract
from local_llm.ollama import OllamaClient

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "samples"
SCHEMA = json.loads((SAMPLES / "invoice.schema.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((SAMPLES / "invoice-expected.json").read_text(encoding="utf-8"))


def test_bench_runs_warmup_plus_repeats_and_reads_placement(server):
    s = bench.run_bench(OllamaClient(server.url), "demo-8b:q4", "hello", repeats=2, num_predict=50, num_ctx=2048)
    chats = [r for r in server.requests if r[1] == "/api/chat"]
    assert len(chats) == 3                                  # 1 warm-up + 2 timed
    assert chats[0][2]["options"] == {"num_predict": 50, "seed": 1, "num_ctx": 2048}
    assert s.gen_tps_median == pytest.approx(100.0) and s.placement == "100% GPU" and s.context_length == 4096
    assert s.row().startswith("| demo-8b:q4 | 100% GPU | 4096 |")
    with pytest.raises(ValueError):
        bench.run_bench(OllamaClient(server.url), "m", "x", repeats=0)


def test_extract_sends_the_schema_and_validates(server):
    obj, errs, res = extract.extract(OllamaClient(server.url), "demo-8b:q4", (SAMPLES / "invoice-email.txt").read_text(encoding="utf-8"), SCHEMA)
    assert errs == [] and extract.compare(obj, EXPECTED) == []
    sent = [r for r in server.requests if r[1] == "/api/chat"][-1][2]
    assert sent["format"] == SCHEMA and sent["messages"][0]["role"] == "system"


def test_extract_reports_schema_violations_and_bad_json(server):
    server.chat_reply = json.dumps({"vendor": "X", "category": "weather", "extra": 1})
    obj, errs, _ = extract.extract(OllamaClient(server.url), "m", "mail", SCHEMA)
    assert any("category" in e and "not in" in e for e in errs) and any("extra: not allowed" in e for e in errs)
    assert any("invoice_number: required" in e for e in errs)
    server.chat_reply = "Sure! here you go"
    obj, errs, _ = extract.extract(OllamaClient(server.url), "m", "mail", SCHEMA)
    assert obj is None and errs[0].startswith("not valid JSON")


def test_validate_types_and_minimum():
    assert extract.validate({"total_eur": -1}, {"type": "object", "properties": {"total_eur": {"type": ["number", "null"], "minimum": 0}}}) \
        == ["$.total_eur: -1 < minimum 0"]
    assert extract.validate(True, {"type": "integer"})            # bool is not an integer
    assert extract.validate(None, {"type": ["string", "null"]}) == []


def test_parse_json_strips_a_fence():
    assert extract.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_compare_numbers_and_strings():
    assert extract.compare({"a": 4600.001, "b": "x"}, {"a": 4600, "b": "x"}) == []
    assert extract.compare({"a": 1}, {"a": 2}) == ["a: expected 2, got 1"]


def test_cli_extract_models_and_sizing(server, capsys):
    base = ["--host", server.url]
    assert cli.main(base + ["extract", "demo-8b:q4", "--email", str(SAMPLES / "invoice-email.txt"), "--schema",
                            str(SAMPLES / "invoice.schema.json"), "--expected", str(SAMPLES / "invoice-expected.json")]) == 0
    assert "ALL MATCH" in capsys.readouterr().out
    assert cli.main(base + ["models"]) == 0
    assert "100% GPU" in capsys.readouterr().out
    assert cli.main(base + ["sizing", "--vram-gib", "24", "--context", "4096", "--kv-type", "q8_0"]) == 0
    out = capsys.readouterr().out
    assert "demo-8b:q4" in out and "FITS" in out and "DOES NOT FIT" in out        # the 40 GiB model cannot fit in 24 GiB


def test_cli_bench_unloads_unless_kept(server, capsys):
    assert cli.main(["--host", server.url, "bench", "demo-8b:q4", "--repeats", "1"]) == 0
    assert "| demo-8b:q4 |" in capsys.readouterr().out
    assert server.requests[-1][2]["keep_alive"] == 0


def test_cli_refuses_remote_host_by_default(capsys):
    assert cli.main(["--host", "https://api.example.com", "models"]) == 2
    assert "non-local" in capsys.readouterr().err


def test_cli_probe_exit_codes(server, capsys, monkeypatch):
    monkeypatch.setattr(cli, "KNOWN_SERVERS", {"fake": server.url + "/v1"})
    assert cli.main(["probe"]) == 0
    monkeypatch.setattr(cli, "KNOWN_SERVERS", {"dead": "http://127.0.0.1:9/v1"})
    assert cli.main(["probe", "--timeout", "1"]) == 1
