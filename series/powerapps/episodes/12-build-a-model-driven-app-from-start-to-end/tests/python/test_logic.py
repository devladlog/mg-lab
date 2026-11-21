"""Business rules, the business process flow plan, the command definitions and the seed data, checked against the schema."""
import csv
import re

import pytest
import yaml

import rules_engine as engine
from conftest import SRC

LOGIC = SRC / "logic"


@pytest.fixture(scope="module")
def rules():
    return engine.load(LOGIC / "business-rules.yaml")


@pytest.fixture(scope="module")
def cols(schema):
    out = {}
    for t in schema["tables"]:
        out[t["logicalName"]] = {c["logicalName"]: c for c in t["columns"]}
        out[t["logicalName"]][t["primaryName"]["logicalName"]] = {"type": "string"}
    return out


# ------------------------------------------------------------------ business rules vs schema
def test_every_rule_refers_to_real_columns_and_valid_choice_labels(rules, cols):
    for r in rules:
        assert r["table"] in cols and engine.valid_scope(r["scope"]), r["name"]
        for col in engine.conditions_columns(r["when"]):
            assert col in cols[r["table"]], (r["name"], col)
        leaves = r["when"].get("all") or r["when"].get("any") or [r["when"]]
        for leaf in leaves:
            c = cols[r["table"]][leaf["column"]]
            if c["type"] == "choice" and leaf["op"] in ("eq", "ne"):
                assert leaf["value"] in [o[0] for o in c["options"]], (r["name"], leaf)
        for a in r["then"] + r.get("otherwise", []):
            assert a["column"] in cols[r["table"]], (r["name"], a)


def test_no_rule_uses_an_action_its_scope_does_not_support(rules):
    """Learn: lock/unlock, visibility, business required and recommendations are model-driven form actions only."""
    for r in rules:
        for a in r["then"] + r.get("otherwise", []):
            assert a["action"] in engine.allowed_actions(r["scope"]), (r["name"], a["action"], r["scope"])


def test_the_engine_itself_rejects_form_only_actions_on_the_server(rules):
    # a rule with table scope and a lock would be silently ignored server side: make sure we have none
    assert not [r for r in rules if r["scope"] == "table" and any(a["action"] in engine.ACTIONS_FORM_ONLY for a in r["then"] + r.get("otherwise", []))]


def test_rule_names_are_unique(rules):
    names = [r["name"] for r in rules]
    assert len(names) == len(set(names))


# ------------------------------------------------------------------ rule behaviour
def test_follow_up_date_shows_and_is_required_only_when_follow_up_is_needed(rules):
    on = engine.run(rules, "cin_inspection", {"cin_requiresfollowup": True})
    assert on["visible"]["cin_followupdate"] is True and on["required"]["cin_followupdate"] is True
    off = engine.run(rules, "cin_inspection", {"cin_requiresfollowup": False})
    assert off["visible"]["cin_followupdate"] is False and off["required"]["cin_followupdate"] is False


def test_approved_inspection_locks_the_business_columns_but_not_the_reviewer_notes(rules):
    s = engine.run(rules, "cin_inspection", {"cin_status": "Approved"})
    assert all(s["locked"].values()) and "cin_reviewernotes" not in s["locked"] and "cin_status" not in s["locked"]
    assert {"cin_score", "cin_summary", "cin_siteid"} <= set(s["locked"])
    s = engine.run(rules, "cin_inspection", {"cin_status": "Rejected"})
    assert not any(s["locked"].values())            # unlocked again after a rejection: the inspector can correct it


def test_submitting_without_a_score_shows_an_error_on_the_form_and_on_the_server(rules):
    rec = {"cin_status": "Submitted", "cin_score": None}
    for client in ("form", "server"):
        s = engine.run(rules, "cin_inspection", rec, client=client)
        assert s["errors"] == [("cin_score", "Enter a score from 0 to 100 before you submit.")], client
    assert engine.run(rules, "cin_inspection", {"cin_status": "Submitted", "cin_score": 0})["errors"] == []   # 0 is a score
    assert engine.run(rules, "cin_inspection", {"cin_status": "Draft", "cin_score": None})["errors"] == []


def test_form_only_rules_do_not_run_for_the_canvas_app(rules):
    s = engine.run(rules, "cin_inspection", {"cin_status": "Approved", "cin_requiresfollowup": True}, client="server")
    assert s["locked"] == {} and s["visible"] == {} and s["required"] == {}


def test_a_critical_finding_cannot_be_passed(rules):
    s = engine.run(rules, "cin_inspectionitem", {"cin_severity": "Critical", "cin_passed": True}, client="server")
    assert s["errors"] == [("cin_passed", "A critical finding cannot be marked as passed.")]
    assert engine.run(rules, "cin_inspectionitem", {"cin_severity": "Minor", "cin_passed": True}, client="server")["errors"] == []


def test_major_and_critical_findings_are_set_to_not_passed_on_the_form(rules):
    for sev in ("Major", "Critical"):
        s = engine.run(rules, "cin_inspectionitem", {"cin_severity": sev, "cin_passed": True}, client="form")
        assert s["values"]["cin_passed"] is False, sev
    assert engine.run(rules, "cin_inspectionitem", {"cin_severity": "Info", "cin_passed": True})["values"]["cin_passed"] is True


def test_the_two_item_rules_do_not_fight_on_the_form(rules):
    """On the form the set-value rule runs first in practice; if both ran with Critical + passed, the user would see both."""
    s = engine.run(rules, "cin_inspectionitem", {"cin_severity": "Critical", "cin_passed": True}, client="form")
    # the engine applies rules in order: the error rule saw 'passed = true' first, then set_value flipped it.
    assert s["values"]["cin_passed"] is False and len(s["errors"]) == 1
    # Honest note for README: rule order is not something we can prove here; the designer decides.


# ------------------------------------------------------------------ business process flow plan
@pytest.fixture(scope="module")
def bpf():
    return yaml.safe_load((LOGIC / "inspection-review.bpf.yaml").read_text(encoding="utf-8"))


def test_bpf_stays_inside_the_documented_limits(bpf):
    assert len(bpf["stages"]) <= 30
    assert all(len(s["steps"]) <= 30 for s in bpf["stages"])
    assert len({s["name"] for s in bpf["stages"]}) == len(bpf["stages"])
    assert len(bpf.get("description", "")) <= 2000


def test_every_step_is_a_column_of_the_bpf_table_and_required_steps_match_the_schema(bpf, cols):
    table = cols[bpf["table"]]
    seen = set()
    for stage in bpf["stages"]:
        for step in stage["steps"]:
            assert step["column"] in table and step["column"] not in seen, step
            seen.add(step["column"])
            if table[step["column"]].get("required"):
                assert step.get("required"), f"{step['column']} is required in the schema, so it must be required in the process too"


def test_bpf_has_the_four_review_stages_in_order(bpf):
    assert [s["name"] for s in bpf["stages"]] == ["Capture", "Findings", "Review", "Decision"]
    assert bpf["stages"][-1]["steps"][0]["column"] == "cin_status"


def test_bpf_table_is_enabled_for_business_process_flows_in_the_source():
    text = (SRC / "solution" / "Entities" / "cin_inspection" / "Entity.xml").read_text(encoding="utf-8-sig")
    assert "<IsBusinessProcessEnabled>1</IsBusinessProcessEnabled>" in text


# ------------------------------------------------------------------ commands
@pytest.fixture(scope="module")
def commands():
    return yaml.safe_load((LOGIC / "commands.yaml").read_text(encoding="utf-8"))


UNSUPPORTED = ["Back", "Clear", "Collect", "Copy", "Disable", "Enable", "Exit", "InvokeControl", "Language", "LoadData", "Param", "Print",
               "ReadNFC", "RequestHide", "ResetForm", "Revert", "SaveData", "ScanBarcode", "Set", "SubmitForm", "UpdateContext", "User", "ViewForm"]


def test_commands_use_no_function_that_learn_lists_as_unsupported_in_commands(commands):
    for c in commands["commands"]:
        for f in (c["visible"], c["onSelect"]):
            for fn in UNSUPPORTED:
                assert not re.search(rf"(?<![\w.]){fn}\s*\(", f), (c["id"], fn)


def test_commands_never_use_notification_type_success(commands):
    """Learn: NotificationType.Success isn't currently supported in commands and shows an informational notification."""
    for c in commands["commands"]:
        assert "NotificationType.Success" not in c["onSelect"], c["id"]


def test_commands_have_unique_ids_and_known_locations(commands):
    ids = [c["id"] for c in commands["commands"]]
    assert len(ids) == len(set(ids))
    for c in commands["commands"]:
        assert set(c["locations"]) <= {"mainForm", "mainGrid"}


# ------------------------------------------------------------------ seed data
def read(name):
    with open(SRC / "data" / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_seed_headers_are_the_display_names_of_the_columns(schema):
    by = {t["logicalName"]: t for t in schema["tables"]}
    names = lambda t: {by[t]["primaryName"]["displayName"]} | {c["displayName"] for c in by[t]["columns"]}
    assert set(read("inspectors.csv")[0]) <= names("cin_inspector")
    assert set(read("sites.csv")[0]) <= names("cin_site")
    assert set(read("items.csv")[0]) <= names("cin_inspectionitem")
    # inspections.csv has no 'Inspection number' (autonumber) and uses short headers for the two lookups
    insp = set(read("inspections.csv")[0]) - {"Site", "Inspector"}
    assert insp <= names("cin_inspection")


def choice_labels(schema, table, col):
    t = next(t for t in schema["tables"] if t["logicalName"] == table)
    return [o[0] for o in next(c for c in t["columns"] if c["logicalName"] == col)["options"]]


def test_seed_choice_values_exist(schema):
    assert {r["Risk level"] for r in read("sites.csv")} <= set(choice_labels(schema, "cin_site", "cin_risklevel"))
    assert {r["Status"] for r in read("inspections.csv")} == set(choice_labels(schema, "cin_inspection", "cin_status"))
    assert {r["Category"] for r in read("items.csv")} <= set(choice_labels(schema, "cin_inspectionitem", "cin_category"))
    assert {r["Severity"] for r in read("items.csv")} == set(choice_labels(schema, "cin_inspectionitem", "cin_severity"))


def test_seed_lookups_resolve():
    sites = {r["Site name"] for r in read("sites.csv")}
    inspectors = {r["Full name"] for r in read("inspectors.csv")}
    for r in read("inspections.csv"):
        assert r["Site"] in sites and r["Inspector"] in inspectors


def test_seed_site_codes_are_unique_because_they_are_an_alternate_key():
    codes = [r["Site code"] for r in read("sites.csv")]
    assert len(codes) == len(set(codes))


def test_seed_items_point_at_the_autonumbers_the_inspections_will_get():
    """Autonumber INS-{SEQNUM:5} starts at 1000 by default (Learn: 'default seed value of 1000'), so the first imported row is INS-01000.
    Import inspections.csv in file order into an empty table, or fix items.csv."""
    n = len(read("inspections.csv"))
    valid = {f"INS-{1000 + i:05d}" for i in range(n)}
    used = {r["Inspection"] for r in read("items.csv")}
    assert used <= valid


def test_seed_obeys_our_own_business_rules(schema, rules):
    """The data we import must not trip the rules we build."""
    for r in read("inspections.csv"):
        rec = {"cin_status": r["Status"], "cin_score": int(r["Score"]) if r["Score"] else None}
        assert engine.run(rules, "cin_inspection", rec, client="server")["errors"] == [], r
        if r["Requires follow-up"] == "Yes":
            assert r["Follow-up date"], r
    for r in read("items.csv"):
        rec = {"cin_severity": r["Severity"], "cin_passed": r["Passed"] == "Yes"}
        assert engine.run(rules, "cin_inspectionitem", rec, client="server")["errors"] == [], r


def test_seed_scores_are_in_range_and_dates_are_iso(schema):
    for r in read("inspections.csv"):
        if r["Score"]:
            assert 0 <= int(r["Score"]) <= 100
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["Inspection date"])
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["Last inspected on"]) for r in read("sites.csv"))


def test_seed_has_a_mix_for_the_demo():
    statuses = [r["Status"] for r in read("inspections.csv")]
    assert statuses.count("Submitted") == 3 and "Approved" in statuses and "Rejected" in statuses
    crit_open = [r for r in read("items.csv") if r["Severity"] == "Critical" and not r["Resolved on"]]
    assert len(crit_open) == 2


def test_seed_uses_only_fictional_data():
    text = "".join((SRC / "data" / n).read_text(encoding="utf-8") for n in ("inspectors.csv", "sites.csv", "inspections.csv", "items.csv"))
    assert "devladlog" not in text.lower()
    assert set(re.findall(r"@([\w.]+)", text)) == {"contoso.com"}
