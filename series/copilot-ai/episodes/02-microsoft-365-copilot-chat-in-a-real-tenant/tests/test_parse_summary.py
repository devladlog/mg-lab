import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot_chat_audit.parse import load_records, to_interaction  # noqa: E402
from copilot_chat_audit.summary import format_text, load_user_list, summarise  # noqa: E402

SAMPLE = ROOT / "src" / "samples" / "copilot-interactions-sample.csv"


def sample():
    return load_records(SAMPLE)


def test_csv_loads_only_copilot_interactions_and_counts_skips():
    r = sample()
    assert len(r.interactions) == 8
    assert r.skipped_other_operations == 1  # the FileAccessed row
    assert r.skipped_unreadable == 1        # the broken AuditData row


def test_web_search_is_detected_from_aisystemplugin_id():
    items = {i.record_id[-2:]: i for i in sample().interactions}
    assert items["01"].web_search and items["03"].web_search and items["08"].web_search
    assert not items["02"].web_search


def test_agent_resources_labels_and_models():
    items = {i.record_id[-2:]: i for i in sample().interactions}
    agent = items["06"]
    assert agent.agent_name == "Vendor FAQ Agent" and agent.agent_id.startswith("CopilotStudio.Declarative.")
    assert agent.app_identity.startswith("Copilot.Studio.")
    assert agent.resources == 1 and agent.labelled_resources == 0
    assert items["05"].labelled_resources == 1
    assert items["04"].models == ["Anthropic"]


def test_flags():
    items = {i.record_id[-2:]: i for i in sample().interactions}
    assert items["07"].jailbreak and items["07"].dlp_deferred == 2
    assert not items["01"].jailbreak


def test_summary_numbers():
    s = summarise(sample().interactions)
    assert s["interactions"] == 8 and s["users"] == 5
    assert s["byAppHost"]["BizChat"] == 5
    assert s["webSearch"] == {"count": 3, "share": 0.375}
    assert s["withAccessedResources"] == 2 and s["withSensitivityLabels"] == 1
    assert s["agents"] == {"Vendor FAQ Agent": 1}
    assert s["models"] == {"OpenAI": 2, "Anthropic": 2}
    assert s["flags"] == {"jailbreakDetected": 1, "xpiaDetected": 0, "dlpEvaluationDeferred": 1}
    assert s["threads"] == 7  # records 1 and 2 share a thread


def test_licence_split_uses_the_licensed_list():
    licensed = load_user_list((ROOT / "src" / "samples" / "licensed-users.txt").read_text())
    s = summarise(sample().interactions, licensed=licensed)
    assert s["licence"]["licensedInteractions"] == 1
    assert s["licence"]["unlicensedInteractions"] == 7
    assert "alex.demo@contoso.example" in s["licence"]["unlicensedUsers"]
    assert "riley.demo@contoso.example" not in s["licence"]["unlicensedUsers"]


def test_since_filter():
    s = summarise(sample().interactions, since=datetime(2026, 11, 21))
    assert s["interactions"] == 3


def test_user_list_parsing():
    assert load_user_list("# c\nA@x.com, b@x.com\n\n  c@x.com # trailing\n") == {"a@x.com", "b@x.com", "c@x.com"}


def test_appidentity_at_top_level_and_xpia(tmp_path):
    audit = {
        "Operation": "CopilotInteraction", "UserId": "Alex.Demo@contoso.example", "CreationTime": "2026-11-21T01:02:03",
        "AppIdentity": "Copilot.MicrosoftCopilot.BizChat",
        "CopilotEventData": {"AppHost": "Bing", "AccessedResources": [{"Name": "x", "XPIADetected": True}], "Messages": []},
    }
    i = to_interaction(audit)
    assert i.app_identity == "Copilot.MicrosoftCopilot.BizChat"
    assert i.xpia and i.user == "alex.demo@contoso.example"


def test_json_shapes(tmp_path):
    audit = {"Operation": "CopilotInteraction", "UserId": "a@x", "CopilotEventData": {"AppHost": "Teams"}}
    (tmp_path / "a.json").write_text(json.dumps([audit]))
    (tmp_path / "b.json").write_text(json.dumps({"value": [{"AuditData": json.dumps(audit), "UserIds": "a@x"}]}))
    (tmp_path / "c.jsonl").write_text(json.dumps(audit) + "\n" + json.dumps(audit) + "\n")
    assert len(load_records(tmp_path / "a.json").interactions) == 1
    assert len(load_records(tmp_path / "b.json").interactions) == 1
    assert len(load_records(tmp_path / "c.jsonl").interactions) == 2


def test_bom_csv(tmp_path):
    p = tmp_path / "e.csv"
    audit = json.dumps({"Operation": "CopilotInteraction", "UserId": "a@x", "CopilotEventData": {}})
    p.write_bytes(b"\xef\xbb\xbf" + f'UserIds,AuditData\na@x,"{audit.replace(chr(34), chr(34) * 2)}"\n'.encode())
    assert len(load_records(p).interactions) == 1


def test_empty_summary_does_not_divide_by_zero():
    s = summarise([])
    assert s["interactions"] == 0 and s["webSearch"]["share"] == 0.0
    assert "0 user(s)" in format_text(s)


def test_sample_contains_no_real_identifiers():
    text = SAMPLE.read_text(encoding="utf-8").lower()
    assert "onmicrosoft.com" not in text and "devladlog" not in text
