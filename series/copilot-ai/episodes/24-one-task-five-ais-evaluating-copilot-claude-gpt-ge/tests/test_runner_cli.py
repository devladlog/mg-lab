import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from five_ais import blind, cli, runner
from five_ais import providers as P

SAMPLES = Path(__file__).resolve().parents[1] / "src" / "samples"
TASKS = json.loads((SAMPLES / "tasks.json").read_text(encoding="utf-8"))
ANSWERS = {  # what a perfect AI would say for the tasks below (kept short on purpose)
    "policy-unanswerable": "NOT STATED", "graph-cmdlet": "Get-MgSubscribedSku",
    "arithmetic-vat": "16,100 then 19,803 euros.",
}
SMALL = [t for t in TASKS if t["id"] in ANSWERS]


def fake_transport(reply_for):
    def t(url, payload, headers, timeout):
        text = reply_for(payload)
        if "api.anthropic.com" in url:
            return {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 10, "output_tokens": 5}, "stop_reason": "end_turn"}
        if "openai.com" in url:
            return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
        if "googleapis" in url:
            return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}
        return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    return t


def question_of(payload):
    return json.dumps(payload)


def answer_for(payload):
    q = question_of(payload)
    return next((a for tid, a in ANSWERS.items() if {"policy-unanswerable": "daily meal allowance", "graph-cmdlet": "subscribed SKUs",
                                                      "arithmetic-vat": "Fabrikam Cloud costs"}[tid] in q), "I do not know")


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "x")
    c = json.loads((SAMPLES / "config.json").read_text(encoding="utf-8"))
    for p in c["providers"]:
        if p.get("model", "").startswith("REPLACE"):
            p["model"] = "test-model"
    c["prices"]["gpt"] = {"input_per_million": 2.0, "output_per_million": 10.0}
    (tmp_path / "copilot-answers.json").write_text(json.dumps({**{t["id"]: "" for t in TASKS}, **ANSWERS}), encoding="utf-8")
    return c, tmp_path


def test_full_run_scores_each_provider_and_isolates_failures(cfg):
    c, base = cfg
    provs = runner.build_providers(c, transport=fake_transport(answer_for), base_dir=base)
    # break one provider: it must not stop the others
    provs[2].transport = lambda *a: (_ for _ in ()).throw(ConnectionError("cannot reach host"))
    res = runner.run(c, SMALL, provs)
    s = runner.summarise(res)
    assert set(s) == {"copilot", "claude", "gpt", "gemini", "local"}
    assert s["claude"]["mean_score"] == 1.0 and s["local"]["full_passes"] == 3 and s["copilot"]["mean_score"] == 1.0
    assert s["gpt"]["errors"] == 3 and s["gpt"]["mean_score"] == 0.0           # errors score zero, they are not skipped
    assert s["copilot"]["mean_seconds"] is None                                 # not measured for manual answers
    assert s["claude"]["input_tokens"] == 30 and s["claude"]["output_tokens"] == 15


def test_cost_uses_config_prices_only(cfg):
    c, base = cfg
    res = runner.run(c, SMALL, runner.build_providers(c, ["gpt", "claude"], fake_transport(answer_for), base), 1)
    s = runner.summarise(res)
    assert s["gpt"]["cost"] == pytest.approx((30 * 2.0 + 15 * 10.0) / 1e6) and s["claude"]["cost"] == 0.0


def test_repeats_multiply_api_answers_but_not_manual_ones(cfg):
    c, base = cfg
    res = runner.run(c, SMALL[:1], runner.build_providers(c, ["copilot", "claude"], fake_transport(answer_for), base), repeats=3)
    n = {pid: sum(r["provider"] == pid for r in res["rows"]) for pid in ("copilot", "claude")}
    assert n == {"copilot": 1, "claude": 3}


def test_same_prompt_for_everyone_in_inline_mode(cfg):
    c, base = cfg
    seen = []
    def t(url, payload, headers, timeout):
        seen.append(json.dumps(payload))
        return fake_transport(answer_for)(url, payload, headers, timeout)
    runner.run(c, SMALL[:1], runner.build_providers(c, ["claude", "gpt", "gemini", "local"], t, base))
    expected = c["instructions"] + "\n\n" + SMALL[0]["question"]
    assert len(seen) == 4 and all(json.dumps(expected)[1:-1] in s for s in seen)
    assert not any('"system"' in s or '"instructions"' in s for s in seen)       # nobody got a separate system field


def test_report_has_scores_categories_errors_and_failed_checks(cfg):
    c, base = cfg
    provs = runner.build_providers(c, transport=fake_transport(answer_for), base_dir=base)
    provs[2].transport = lambda *a: (_ for _ in ()).throw(ConnectionError("cannot reach host"))
    text = runner.report(runner.run(c, SMALL, provs))
    assert "| Claude |" in text and "grounded-qa" in text and "Errors (scored 0" in text and "cannot reach host" in text
    assert "code execution OFF" in text and "placeholders are zero" in text


def test_plan_flags_problems(cfg, monkeypatch):
    c, base = cfg
    monkeypatch.delenv("GEMINI_API_KEY")
    c["providers"][4]["model"] = "REPLACE-x"
    lines = runner.plan(c, TASKS, runner.build_providers(c, base_dir=base), 1)
    assert lines[0].startswith("5 providers x 7 tasks x 1 repeat(s) = 35")
    assert any("gemini" in l and "GEMINI_API_KEY not set" in l for l in lines)
    assert any("local" in l and "model not set" in l for l in lines)


def test_config_validation_and_only_filter(cfg):
    c, base = cfg
    with pytest.raises(ValueError, match="unknown provider"):
        runner.build_providers(c, ["nope"], base_dir=base)
    (base / "bad.json").write_text(json.dumps({"providers": [{"id": "a", "kind": "local"}, {"id": "a", "kind": "local"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        runner.load_config(base / "bad.json")


def test_blind_sheet_hides_names_and_unblind_attaches_scores(cfg):
    c, base = cfg
    res = runner.run(c, SMALL, runner.build_providers(c, ["claude", "gpt", "local"], fake_transport(answer_for), base))
    sheet, key = blind.make_sheet(res, seed=1)
    assert all(name not in sheet for name in ("claude", "gpt", "local", "Claude"))
    assert set(key["graph-cmdlet"].values()) == {"claude", "gpt", "local"} and set(key["graph-cmdlet"]) == {"A", "B", "C"}
    assert blind.make_sheet(res, seed=1)[1] == key            # same seed, same shuffle: the key is reproducible
    label_of_gpt = next(k for k, v in key["graph-cmdlet"].items() if v == "gpt")
    out = blind.unblind(res, key, {"graph-cmdlet": {label_of_gpt: 5}})
    gpt_row = next(r for r in out["rows"] if r["provider"] == "gpt" and r["task"] == "graph-cmdlet")
    assert gpt_row["human_score"] == 5.0
    assert runner.summarise(out)["gpt"]["human_mean"] == 5.0 and runner.summarise(out)["claude"]["human_mean"] is None


@pytest.mark.parametrize("scores,msg", [({"nope": {"A": 3}}, "unknown task"), ({"graph-cmdlet": {"Z": 3}}, "no answer labelled"),
                                        ({"graph-cmdlet": {"A": 9}}, "1 to 5"), ({"graph-cmdlet": {"A": True}}, "1 to 5")])
def test_unblind_rejects_bad_scores(cfg, scores, msg):
    c, base = cfg
    res = runner.run(c, SMALL, runner.build_providers(c, ["claude"], fake_transport(answer_for), base))
    _, key = blind.make_sheet(res)
    with pytest.raises(ValueError, match=msg):
        blind.unblind(res, key, scores)


def test_blind_sheet_leaves_out_errors_and_empty_answers(cfg):
    c, base = cfg
    provs = runner.build_providers(c, ["claude", "gpt"], fake_transport(answer_for), base)
    provs[1].transport = lambda *a: (_ for _ in ()).throw(ConnectionError("down"))
    _, key = blind.make_sheet(runner.run(c, SMALL, provs))
    assert all(list(v.values()) == ["claude"] for v in key.values())


# ---- the CLI over real HTTP against a local stand-in (tests only) -----------------------------------------------------

@pytest.fixture()
def http_server():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = answer_for(body)
            data = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 4, "completion_tokens": 2}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/v1"
    s.shutdown(); s.server_close()


def test_cli_end_to_end(cfg, http_server, tmp_path, capsys, monkeypatch):
    c, base = cfg
    c["providers"] = [p for p in c["providers"] if p["id"] in ("copilot", "local")]
    c["providers"][1]["base_url"] = http_server
    (base / "config.json").write_text(json.dumps(c), encoding="utf-8")
    (base / "tasks.json").write_text(json.dumps(SMALL), encoding="utf-8")
    cfgp, tp, out = str(base / "config.json"), str(base / "tasks.json"), str(base / "results.json")
    assert cli.main(["plan", "--config", cfgp, "--tasks", tp]) == 0
    assert "2 providers x 3 tasks" in capsys.readouterr().out
    assert cli.main(["run", "--config", cfgp, "--tasks", tp, "--out", out]) == 0
    text = capsys.readouterr().out
    assert "| Microsoft Copilot Chat (collected by hand) |" in text and "1.00" in text
    res = json.loads(Path(out).read_text(encoding="utf-8"))
    assert len(res["rows"]) == 6 and all(r["score"] == 1.0 for r in res["rows"])
    # blind -> score -> unblind
    sheet, key = str(base / "sheet.md"), str(base / "key.json")
    assert cli.main(["blind", out, "--sheet", sheet, "--key", key]) == 0
    k = json.loads(Path(key).read_text(encoding="utf-8"))
    scores = base / "scores.json"
    scores.write_text(json.dumps({"graph-cmdlet": {lab: 4 for lab in k["graph-cmdlet"]}}), encoding="utf-8")
    assert cli.main(["unblind", out, "--key", key, "--scores", str(scores)]) == 0
    assert "4.0" in capsys.readouterr().out
    assert cli.main(["report", out]) == 0


def test_cli_prompts_prints_exact_text_and_writes_template(cfg, tmp_path, capsys):
    c, base = cfg
    (base / "config.json").write_text(json.dumps(c), encoding="utf-8")
    (base / "tasks.json").write_text(json.dumps(SMALL), encoding="utf-8")
    tpl = base / "tpl.json"
    assert cli.main(["prompts", "--config", str(base / "config.json"), "--tasks", str(base / "tasks.json"), "--write-template", str(tpl)]) == 0
    out = capsys.readouterr().out
    assert c["instructions"] in out and SMALL[0]["question"] in out
    assert json.loads(tpl.read_text(encoding="utf-8")) == {t["id"]: "" for t in SMALL}


def test_cli_run_refuses_unready_providers_unless_told(cfg, capsys, monkeypatch):
    c, base = cfg
    monkeypatch.delenv("OPENAI_API_KEY")
    (base / "config.json").write_text(json.dumps(c), encoding="utf-8")
    (base / "tasks.json").write_text(json.dumps(SMALL), encoding="utf-8")
    assert cli.main(["run", "--config", str(base / "config.json"), "--tasks", str(base / "tasks.json"), "--only", "gpt"]) == 2
    assert "OPENAI_API_KEY not set" in capsys.readouterr().err


def test_cli_reports_missing_files(capsys):
    assert cli.main(["report", "nope.json"]) == 2
    assert "error" in capsys.readouterr().err
