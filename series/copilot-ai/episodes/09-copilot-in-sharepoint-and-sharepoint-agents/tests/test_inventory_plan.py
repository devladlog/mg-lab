import csv
import io
from datetime import date
from pathlib import Path

import pytest

from agentfiles import cli, inventory, plan

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "src" / "samples" / "agent-files-export.csv"
TRIAGE = ROOT / "src" / "samples" / "triage.csv"
TODAY = date(2026, 11, 21)


def test_reader_keeps_only_agent_files():
    files, skipped = inventory.read_inventory(EXPORT)
    assert len(files) == 5 and skipped == 1
    vd = files[0]
    assert vd.title == "Vendor Desk" and vd.views_lifetime == 214 and vd.modified == date(2026, 10, 20)


def test_reader_is_case_insensitive_and_tolerates_dates(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("path,AUTHOR,lastmodifiedtime,viewslifetime\nhttps://e.sharepoint.com/a.AGENT,Alex Demo,11/02/2026 4:00:00 PM,x\n",
                 encoding="utf-8")
    files, skipped = inventory.read_inventory(f)
    assert skipped == 0 and files[0].owner == "Alex Demo"
    assert files[0].modified == date(2026, 11, 2) and files[0].views_lifetime == 0


def test_summary_counts():
    files, _ = inventory.read_inventory(EXPORT)
    s = inventory.summarize(files, TODAY)
    assert s["agent_files"] == 5 and s["sites"] == 4
    assert s["never_viewed"] == 1 and s["no_owner"] == 1
    assert s["top_sites"][0] == ("Contoso Vendor Management Office", 2)
    assert s["not_modified_for_days"]["count"] == 2  # Renewals Helper (Apr) and Old Pilot (Jan)


def test_plan_follows_learn_table():
    files, _ = inventory.read_inventory(EXPORT)
    items = {i.file.title: i for i in plan.build_plan(files, plan.read_triage(TRIAGE), TODAY)}
    assert items["Vendor Desk"].path_name == "Use Copilot in SharePoint directly"
    assert items["Renewals Helper"].path_name == "Convert the agent to a skill"
    assert items["Invoice Checker"].path_name == "Upgrade with Microsoft Copilot Agent Builder"
    assert items["Studio Bot"].path_name == "Publish the existing Copilot Studio agent to Microsoft Copilot app"


def test_priority_uses_learns_seven_factors():
    files, _ = inventory.read_inventory(EXPORT)
    items = {i.file.title: i for i in plan.build_plan(files, plan.read_triage(TRIAGE), TODAY)}
    # Invoice Checker: high usage (96>=50), broad, critical, custom instructions, payg, teams = 6 factors
    assert items["Invoice Checker"].score == 6 and items["Invoice Checker"].priority == "high"
    assert set(items["Vendor Desk"].factors) == {"high_usage", "broad_audience", "business_critical", "prominent"}
    assert items["Renewals Helper"].factors == ["custom_instructions"] and items["Renewals Helper"].priority == "medium"
    assert plan.priority_for(0) == "low" and plan.priority_for(2) == "medium" and plan.priority_for(3) == "high"


def test_untriaged_unused_ownerless_agent_is_an_archive_candidate():
    files, _ = inventory.read_inventory(EXPORT)
    items = {i.file.title: i for i in plan.build_plan(files, plan.read_triage(TRIAGE), TODAY)}
    assert items["Old Pilot"].archive_candidate
    assert items["Old Pilot"].path_name == plan.ARCHIVE_PATH
    assert not items["Studio Bot"].archive_candidate


def test_business_critical_agent_is_never_an_archive_candidate(tmp_path):
    files, _ = inventory.read_inventory(EXPORT)
    t = tmp_path / "t.csv"
    t.write_text("Path,Role,BusinessCritical\nhttps://example.sharepoint.com/sites/contoso-pilot/Shared Documents/Old Pilot.agent,site-qa,yes\n",
                 encoding="utf-8")
    item = [i for i in plan.build_plan(files, plan.read_triage(t), TODAY) if i.file.title == "Old Pilot"][0]
    assert not item.archive_candidate and item.path_name == "Use Copilot in SharePoint directly"


def test_sorted_high_priority_first_and_days_left():
    files, _ = inventory.read_inventory(EXPORT)
    items = plan.build_plan(files, plan.read_triage(TRIAGE), TODAY)
    assert [i.priority for i in items] == sorted((i.priority for i in items), key=["high", "medium", "low"].index)
    assert items[0].file.title in {"Invoice Checker", "Studio Bot"}
    assert items[0].days_left == (date(2027, 3, 31) - TODAY).days == 130


def test_unknown_role_is_rejected(tmp_path):
    t = tmp_path / "t.csv"
    t.write_text("Path,Role\nhttps://e.sharepoint.com/a.agent,magic\n", encoding="utf-8")
    with pytest.raises(ValueError, match="magic"):
        plan.read_triage(t)


def test_teams_and_payg_notes_come_from_learn():
    files, _ = inventory.read_inventory(EXPORT)
    ic = [i for i in plan.build_plan(files, plan.read_triage(TRIAGE), TODAY) if i.file.title == "Invoice Checker"][0]
    assert any("same time" in n for n in ic.notes) and any("pay-as-you-go" in n for n in ic.notes)


def test_triage_template_round_trip(tmp_path):
    files, _ = inventory.read_inventory(EXPORT)
    out = tmp_path / "t.csv"
    plan.write_triage_template(files, out)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 5 and list(rows[0].keys()) == plan.TRIAGE_COLUMNS
    assert plan.read_triage(out) is not None  # an empty template is a valid triage sheet


def test_markdown_and_csv_render():
    files, _ = inventory.read_inventory(EXPORT)
    items = plan.build_plan(files, plan.read_triage(TRIAGE), TODAY)
    md = plan.render_markdown(items, TODAY)
    assert "130 days left" in md and "| high | Invoice Checker |" in md
    buf = io.StringIO()
    plan.render_csv(items, buf)
    assert buf.getvalue().splitlines()[0].startswith("Priority,Title")


def test_cli_plan_and_inventory(capsys):
    assert cli.main(["inventory", str(EXPORT), "--today", "2026-11-21"]) == 0
    assert ".agent files: 5 on 4 site(s)" in capsys.readouterr().out
    assert cli.main(["plan", str(EXPORT), "--triage", str(TRIAGE), "--today", "2026-11-21"]) == 0
    assert "Recommended path" in capsys.readouterr().out
