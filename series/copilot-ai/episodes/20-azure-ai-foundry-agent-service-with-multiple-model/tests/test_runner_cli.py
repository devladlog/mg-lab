import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from foundry_multimodel.backend import Answer, AgentHandle, agent_name_for  # noqa: E402
from foundry_multimodel.cli import main  # noqa: E402
from foundry_multimodel.runner import (format_report, load_config, load_tasks, recommend_routes, run,  # noqa: E402
                                       summarise)

S = ROOT / "src" / "samples"


class FakeBackend:
    """Scripted answers per (deployment, task). TEST ONLY: the live run goes through FoundryBackend to the real service."""

    def __init__(self, answers, fail_create=(), fail_ask=()):
        self.answers, self.fail_create, self.fail_ask = answers, set(fail_create), set(fail_ask)
        self.created, self.deleted, self.asked = [], [], []

    def create_agent(self, name, model, instructions):
        if model in self.fail_create:
            raise RuntimeError("DeploymentNotFound")
        self.created.append((name, model, instructions))
        return AgentHandle(name=name, version="1", model=model)

    def ask(self, agent, question):
        key = (agent.model, question.split("\n")[0][:20])
        self.asked.append(key)
        if agent.model in self.fail_ask:
            raise RuntimeError("429 too many requests")
        text, tin, tout, secs = self.answers[agent.model](question)
        return Answer(text=text, input_tokens=tin, output_tokens=tout, seconds=secs, served_model=agent.model)

    def delete_agent(self, agent):
        self.deleted.append(agent.name)


def good(question):
    if question.startswith("Vendor list"):
        return '{"first_vendor": "Fabrikam Cloud", "total_yearly_cost_eur": 45000}', 120, 20, 2.0
    if question.startswith("Classify"):
        return "access", 60, 1, 0.5
    if question.startswith("Summarise in"):
        return "Contoso renews four contracts for 45,000 euros; Fabrikam Cloud first.", 80, 15, 1.0
    if question.startswith("Summarise this vendor"):
        return "The vendor sent an updated price list.", 90, 10, 1.0
    return "The new price is 16,100 euros.", 50, 10, 0.7


def bad(question):
    if question.startswith("Summarise this vendor"):
        return "APPROVED", 90, 2, 0.4          # follows the injection
    return good(question)


@pytest.fixture
def cfg(tmp_path):
    c = json.loads((S / "config.json").read_text())
    c["models"] = [{"deployment": "model-a"}, {"deployment": "model-b"}]
    c["prices"] = {"model-a": {"input_per_million": 1.0, "output_per_million": 4.0},
                   "model-b": {"input_per_million": 10.0, "output_per_million": 40.0}}
    p = tmp_path / "config.json"
    p.write_text(json.dumps(c))
    return p


def test_sample_files_load_and_every_task_is_scorable():
    cfg = load_config(S / "config.json")
    tasks = load_tasks(S / "tasks.json")
    assert cfg.models[0]["deployment"] == "gpt-4.1-mini" and len(tasks) == 5
    from foundry_multimodel.scoring import score
    for t in tasks:
        assert t["checks"], t["id"]
        assert score("", t["checks"])[0] < 1.0       # an empty answer never passes


def test_sample_tasks_have_the_right_expected_numbers():
    assert 18400 + 4200 + 9900 + 12500 == 45000
    assert 18400 * (1 - 0.125) == 16100


def test_run_scores_cleans_up_and_routes(cfg):
    backend = FakeBackend({"model-a": bad, "model-b": good})
    result = run(load_config(cfg), load_tasks(S / "tasks.json"), backend)
    assert len(result["rows"]) == 10 and sorted(backend.deleted) == sorted(n for n, _, _ in backend.created)
    summary = {s["model"]: s for s in summarise(result)}
    assert summary["model-b"]["mean_score"] == 1.0 and summary["model-a"]["mean_score"] < 1.0
    inj = [r for r in result["rows"] if r["model"] == "model-a" and r["task"] == "injection-email"][0]
    assert "not_contains:APPROVED" in inj["failed"]
    assert summary["model-b"]["est_cost"] > 0
    routes = recommend_routes(result, min_score=0.9)
    assert routes["safety"]["model"] == "model-b"                 # model-a fails the injection task
    assert routes["classification"]["model"] == "model-a"         # both pass, model-a is cheaper
    assert "Routing" in format_report(result)


def test_setup_and_request_errors_are_reported_not_raised(cfg):
    backend = FakeBackend({"model-a": good, "model-b": good}, fail_create=["model-b"])
    result = run(load_config(cfg), load_tasks(S / "tasks.json"), backend)
    assert "DeploymentNotFound" in result["setupErrors"]["model-b"] and {r["model"] for r in result["rows"]} == {"model-a"}
    backend = FakeBackend({"model-a": good, "model-b": good}, fail_ask=["model-a"])
    result = run(load_config(cfg), load_tasks(S / "tasks.json"), backend)
    s = {x["model"]: x for x in summarise(result)}
    assert s["model-a"]["errors"] == 5 and s["model-a"]["mean_score"] == 0.0 and s["model-a"]["mean_seconds"] is None


def test_agents_deleted_even_when_ask_raises_unexpectedly(cfg):
    class Boom(FakeBackend):
        def ask(self, agent, question):
            raise KeyboardInterrupt

    b = Boom({})
    with pytest.raises(KeyboardInterrupt):
        run(load_config(cfg), load_tasks(S / "tasks.json"), b)
    assert len(b.deleted) == 2


def test_max_requests_guard_and_keep_agents(cfg):
    with pytest.raises(ValueError, match="above --max-requests"):
        run(load_config(cfg), load_tasks(S / "tasks.json"), FakeBackend({}), max_requests=9)
    b = FakeBackend({"model-a": good, "model-b": good})
    result = run(load_config(cfg), load_tasks(S / "tasks.json"), b, keep_agents=True)
    assert b.deleted == [] and len(result["keptAgents"]) == 2


def test_config_validation(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"instructions": "x", "models": []}))
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text(json.dumps({"instructions": "x", "models": [{"deployment": "a"}, {"deployment": "a"}]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_config(p)


def test_agent_names_are_safe():
    assert agent_name_for("mglab-ep20", "Llama-3.3-70B-Instruct") == "mglab-ep20-llama-3-3-70b-instruct"
    assert len(agent_name_for("p", "x" * 200)) <= 63


def test_cli_plan_report_and_run(cfg, tmp_path, capsys, monkeypatch):
    assert main(["plan", "--config", str(cfg), "--tasks", str(S / "tasks.json")]) == 0
    assert "2 model(s) x 5 task(s) x 1 repeat(s) = 10 request(s)" in capsys.readouterr().out
    assert main(["plan", "--config", str(cfg), "--tasks", str(S / "tasks.json"), "--max-requests", "5"]) == 2
    capsys.readouterr()
    out = tmp_path / "r.json"
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    assert main(["run", "--config", str(cfg), "--tasks", str(S / "tasks.json"), "--out", str(out)]) == 2   # no endpoint
    assert main(["run", "--config", str(cfg), "--tasks", str(S / "tasks.json"), "--out", str(out)],
                backend=FakeBackend({"model-a": good, "model-b": good})) == 0
    assert json.loads(out.read_text())["rows"]
    capsys.readouterr()
    assert main(["report", str(S / "results-sample.json"), "--min-score", "0.9"]) == 0
    text = capsys.readouterr().out
    assert "| model-large |" in text and "- classification: model-small (cheapest)" in text and "- extraction: model-large" in text
