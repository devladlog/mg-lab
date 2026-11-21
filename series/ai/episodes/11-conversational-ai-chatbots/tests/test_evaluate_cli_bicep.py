import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT, call, say
from helpbot import evaluate as ev
from helpbot.bot import Bot
from helpbot.cli import build_parser, main
from helpbot.session import Session

GOOD = {"product": "Contoso Connect", "symptom": "VPN keeps dropping", "urgency": "high", "contact": "alex.demo@contoso.com"}


def scenarios():
    return {s["id"]: s for s in ev.load_scenarios()}


def test_the_scenario_file_is_well_formed_and_covers_the_hard_situations():
    sc = scenarios()
    assert len(sc) == 7
    for s in sc.values():
        assert s["turns"] and s["checks"] and s["about"]
    assert len(sc["remembers-the-name"]["turns"]) == 10
    assert sc["remembers-the-name"]["informational_modes"] == ["window"]
    assert any("ceo@evil.example" in t for t in sc["injection-and-outsider"]["turns"])
    assert not (set().union(*[s["checks"] for s in sc.values()]) - {
        "tickets", "ticket_fields", "ticket_id_in_last_reply", "handoff", "model_calls_total_max",
        "last_reply_has_any", "last_reply_has_none"})


def run(stub, client, scn_ids, mode="summary", **kw):
    return ev.evaluate(lambda m, scn: Bot(client, "chat", memory_mode=m, **kw), [scenarios()[i] for i in scn_ids], modes=(mode,))


def test_ticket_scenario_passes_when_the_bot_does_what_it_should(stub, client):
    steps = iter([say("Which product?"), say("What is your e-mail?"), call("create_ticket", GOOD), say("INC-1001 is open.")])
    stub.model = lambda req: next(steps)
    [r] = run(stub, client, ["ticket-slots"])
    assert r.passed, r.problems


def test_ticket_scenario_fails_when_the_bot_claims_a_ticket_it_never_made(stub, client):
    stub.model = lambda req: say("Done, INC-1001 is open.")
    [r] = run(stub, client, ["ticket-slots"])
    assert not r.passed and any("expected 1 ticket" in p for p in r.problems) and any("quote the ticket id" in p for p in r.problems)


def test_wrong_urgency_is_a_failure_not_a_pass(stub, client):
    steps = iter([say("?"), say("?"), call("create_ticket", {**GOOD, "urgency": "low"}), say("INC-1001")])
    stub.model = lambda req: next(steps)
    [r] = run(stub, client, ["ticket-slots"])
    assert not r.passed and "urgency" in r.problems[0]


def test_the_two_person_scenarios_pass_by_rule_with_zero_model_calls(stub, client):
    rs = run(stub, client, ["asks-for-a-person", "pede-uma-pessoa"])
    assert all(r.passed for r in rs) and sum(r.model_calls for r in rs) == 0 and stub.requests == []


def test_a_model_that_calls_the_tool_with_an_outsider_address_is_stopped_by_the_validation(stub, client):
    steps = iter([call("create_ticket", {**GOOD, "contact": "ceo@evil.example"}), say("I could not open it.")])
    stub.model = lambda req: next(steps)
    [r] = run(stub, client, ["injection-and-outsider"])
    assert r.passed


def test_a_model_that_invents_a_salary_fails_the_scope_scenario(stub, client):
    stub.model = lambda req: say("A senior developer is usually in band 5, about € 60,000.")
    [r] = run(stub, client, ["out-of-scope"])
    assert not r.passed and any("€" in p for p in r.problems)


def test_the_memory_scenario_compares_both_modes_and_only_the_summary_mode_is_gated(stub, client):
    def model(req):
        if not req.get("stream"):
            return say("Riley Demo works in Finance.")
        if "what is my name" not in req["messages"][-1]["content"]:
            return say("Fine.")
        return say("Your name is Riley." if "Riley" in json.dumps(req["messages"]) else "I'm sorry, I don't know your name.")
    stub.model = model
    results = ev.evaluate(lambda m, scn: Bot(client, "chat", memory_mode=m, history_budget=150, keep_last_turns=1),
                          [scenarios()["remembers-the-name"]])
    by_mode = {r.mode: r for r in results}
    assert by_mode["summary"].passed and not by_mode["window"].passed and by_mode["window"].informational
    ok, bad = ev.gate(results)
    assert ok and bad == []


def test_a_gated_failure_makes_the_gate_fail_and_the_report_says_so(stub, client):
    stub.model = lambda req: say("I am a bot with no memory.")
    results = ev.evaluate(lambda m, scn: Bot(client, "chat", memory_mode=m, history_budget=150, keep_last_turns=1),
                          [scenarios()["remembers-the-name"]])
    ok, bad = ev.gate(results)
    text = ev.format_report(results)
    assert not ok and "remembers-the-name [summary]" in bad[0] and "RESULT: FAIL" in text and "INFO-fail" in text


def test_an_api_failure_is_a_failed_scenario_not_a_crash(stub, client):
    stub.model = lambda req: {"status": 400, "body": {"error": {"code": "x", "message": "bad"}}}
    [r] = run(stub, client, ["ticket-slots"])
    assert not r.passed and "BadRequestError" in r.error
    assert not ev.gate([r])[0]


def test_unknown_check_names_are_errors():
    scn = {"id": "x", "turns": ["a"], "checks": {"tikets": 1}}
    from helpbot.bot import Reply
    assert "unknown check 'tikets'" in ev.check(scn, Session(), [Reply("hi")])[0]


def test_cli_help_lists_both_commands():
    ap = build_parser()
    assert {"chat", "evaluate"} <= set(ap._subparsers._group_actions[0].choices)


def test_cli_requires_an_endpoint(capsys, monkeypatch):
    monkeypatch.delenv("HELPBOT_ENDPOINT", raising=False)
    with pytest.raises(SystemExit) as e:
        main(["evaluate"])
    assert "HELPBOT_ENDPOINT" in str(e.value)


def test_cli_chat_script_end_to_end_with_a_resumed_session(stub, tmp_path, capsys, monkeypatch):
    from helpbot import cli
    from conftest import FakeCredential
    from helpbot.client import make_client
    monkeypatch.setattr(cli, "make_client", lambda endpoint: make_client(endpoint, FakeCredential()))
    script = tmp_path / "dialog.txt"
    script.write_text("my VPN is slow\n", encoding="utf-8")
    stub.model = lambda req: say("Try reconnecting to the VPN.")
    rc = main(["chat", "--endpoint", stub.url, "--store", str(tmp_path / "s"), "--session", "demo-cli-01", "--script", str(script)])
    out = capsys.readouterr().out
    assert rc == 0 and "you> my VPN is slow" in out and "bot> Try reconnecting to the VPN." in out and "state=bot" in out
    script.write_text("and now it is fixed\n", encoding="utf-8")
    main(["chat", "--endpoint", stub.url, "--store", str(tmp_path / "s"), "--session", "demo-cli-01", "--script", str(script)])
    assert len(stub.chats()[-1]["messages"]) == 4                  # system + the first exchange + the new user message


def test_cli_evaluate_exit_code_follows_the_gate(stub, tmp_path, capsys, monkeypatch):
    from helpbot import cli
    from conftest import FakeCredential
    from helpbot.client import make_client
    monkeypatch.setattr(cli, "make_client", lambda endpoint: make_client(endpoint, FakeCredential()))
    stub.model = lambda req: say("Hello.")
    rc = main(["evaluate", "--endpoint", stub.url, "--only", "asks-for-a-person", "--only", "no-details-no-ticket"])
    assert rc == 0 and "RESULT: PASS" in capsys.readouterr().out
    rc = main(["evaluate", "--endpoint", stub.url, "--only", "ticket-slots"])
    assert rc == 1 and "RESULT: FAIL" in capsys.readouterr().out


needs_bicep = pytest.mark.skipif(shutil.which("bicep") is None, reason="Bicep CLI not installed")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    out = tmp_path_factory.mktemp("arm") / "main.json"
    subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--outfile", str(out)], check=True, capture_output=True)
    return json.loads(out.read_text())


@needs_bicep
def test_bicep_is_keyless_with_one_pinned_standard_deployment_and_inference_rights_only(template):
    arm = template["resources"]
    acct = next(r for r in arm if r["type"] == "Microsoft.CognitiveServices/accounts")
    assert acct["kind"] == "OpenAI" and acct["properties"]["disableLocalAuth"] is True
    deps = [r for r in arm if r["type"].endswith("/deployments")]
    assert len(deps) == 1 and deps[0]["sku"]["name"] == "Standard"
    assert deps[0]["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    roles = [r for r in arm if r["type"] == "Microsoft.Authorization/roleAssignments"]
    assert len(roles) == 1 and template["variables"]["openAiUser"] == "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
    assert "a001fd3d" not in json.dumps(template)                   # not Cognitive Services OpenAI Contributor


def test_tool_descriptions_stay_under_the_1024_character_limit_documented_on_learn():
    from helpbot.tools import TOOLS
    for t in TOOLS:
        assert len(t["function"]["description"]) <= 1024
        for p in t["function"]["parameters"]["properties"].values():
            assert len(p.get("description", "")) <= 1024
