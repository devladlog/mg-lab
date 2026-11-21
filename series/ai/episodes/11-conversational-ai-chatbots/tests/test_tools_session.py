import json
import os
import time

import pytest

from helpbot.session import Session, SessionStore
from helpbot.tools import create_ticket, run_tool, wants_human

GOOD = {"product": "Contoso Connect VPN", "symptom": "drops every five minutes", "urgency": "high", "contact": "alex.demo@contoso.com"}


def test_a_complete_ticket_is_created_with_a_sequential_id():
    s = Session()
    r = create_ticket(s, GOOD)
    assert r == {"ok": True, "ticket_id": "INC-1001"} and s.tickets[0]["urgency"] == "high"


@pytest.mark.parametrize("drop", ["product", "symptom", "urgency", "contact"])
def test_each_missing_slot_is_reported_and_nothing_is_created(drop):
    s = Session()
    r = create_ticket(s, {k: v for k, v in GOOD.items() if k != drop})
    assert r["ok"] is False and r["missing"] == [drop] and s.tickets == []


def test_blank_values_count_as_missing():
    assert create_ticket(Session(), {**GOOD, "contact": "   "})["missing"] == ["contact"]


@pytest.mark.parametrize("contact", ["ceo@evil.example", "alex@contoso.com.evil.example", "alex demo@contoso.com", "@contoso.com"])
def test_only_company_addresses_are_accepted(contact):
    s = Session()
    r = create_ticket(s, {**GOOD, "contact": contact})
    assert r["ok"] is False and "@contoso.com" in r["errors"][0] and s.tickets == []


def test_urgency_must_be_one_of_the_enum_even_if_the_schema_said_so():
    r = create_ticket(Session(), {**GOOD, "urgency": "critical"})
    assert r["ok"] is False and "urgency" in r["errors"][0]


def test_the_same_request_twice_returns_the_same_ticket():
    s = Session()
    first = create_ticket(s, GOOD)
    again = create_ticket(s, {**GOOD, "product": "contoso connect vpn"})
    assert again == {"ok": True, "ticket_id": first["ticket_id"], "duplicate": True} and len(s.tickets) == 1


def test_a_conversation_cannot_open_more_than_three_tickets():
    s = Session()
    for i in range(3):
        assert create_ticket(s, {**GOOD, "symptom": f"different problem number {i}"})["ok"]
    r = create_ticket(s, {**GOOD, "symptom": "yet another different problem"})
    assert r["ok"] is False and len(s.tickets) == 3


def test_run_tool_survives_garbage_arguments_and_unknown_tools():
    s = Session()
    assert json.loads(run_tool(s, "create_ticket", "{not json"))["ok"] is False
    assert json.loads(run_tool(s, "create_ticket", "[1,2]"))["ok"] is False
    assert json.loads(run_tool(s, "drop_database", "{}"))["ok"] is False
    assert s.tickets == [] and s.state == "bot"


def test_handoff_tool_flips_the_state_and_trims_the_reason():
    s = Session()
    assert json.loads(run_tool(s, "handoff_to_human", json.dumps({"reason": "x" * 500})))["ok"]
    assert s.state == "handoff" and len(s.handoff_reason) == 200


@pytest.mark.parametrize("text,expected", [
    ("I want to talk to a person", True), ("Can I SPEAK TO A HUMAN please", True),
    ("Preferia falar com uma pessoa", True), ("quero falar com alguém", True), ("Atendimento humano, por favor", True),
    ("My Human Resources portal is down", False), ("the printer has a human-sized jam", False), ("hello", False),
])
def test_wants_human_in_english_and_portuguese_without_false_alarms(text, expected):
    assert wants_human(text) is expected


def test_session_roundtrip_and_expiry(tmp_path):
    store = SessionStore(tmp_path, ttl_seconds=60)
    s = Session(id="demo-session-1", messages=[{"role": "user", "content": "olá, Zé"}], summary="Zé, Porto")
    store.save(s)
    back = store.load("demo-session-1")
    assert back.messages == s.messages and back.summary == "Zé, Porto"
    path = tmp_path / "demo-session-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["updated"] = time.time() - 120
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.load("demo-session-1") is None and not path.exists()


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", "UPPER-CASE-ID", "x", "id with space"])
def test_session_ids_cannot_escape_the_store_directory(tmp_path, bad):
    with pytest.raises(ValueError):
        SessionStore(tmp_path).load(bad)


def test_purge_removes_only_expired_files(tmp_path):
    store = SessionStore(tmp_path, ttl_seconds=60)
    store.save(Session(id="fresh-one-123"))
    store.save(Session(id="stale-one-123"))
    old = time.time() - 600
    os.utime(tmp_path / "stale-one-123.json", (old, old))
    assert store.purge_expired() == 1 and (tmp_path / "fresh-one-123.json").exists()
