"""Dry runs of the two flows against mocked connectors, and the OData text they send."""
from flowkit import run_flow

from d365kit import check_filter, evaluate_filter
from conftest import DIGEST, NOW, WON, load_flow, sample

OPP = "00000000-0000-0000-0000-0000000000b1"
OWNER = "00000000-0000-0000-0000-0000000000e1"


def won_mocks(value=12500, existing=()):
    return {
        "Get_opportunity": {"status": "Succeeded", "body": {
            "name": "Fabrikam laptop refresh", "estimatedvalue": value, "actualvalue": value,
            "_ownerid_value": OWNER, "parentaccountid": {"name": "Fabrikam"}}},
        "List_existing_kickoff_tasks": {"status": "Succeeded", "body": {"value": list(existing)}},
        "Create_kickoff_task": {"status": "Succeeded", "body": {"activityid": "00000000-0000-0000-0000-0000000000d1"}},
        "Tell_finance": {"status": "Succeeded", "body": {}},
    }


def run_won(**kw):
    return run_flow(load_flow(WON), sample("opportunity-won.json"), won_mocks(**kw), now=NOW)


def test_big_deal_gets_a_kickoff_task_and_finance_is_told():
    r = run_won()
    assert r.status == "Succeeded"
    p = r.actions["Create_kickoff_task"].inputs["parameters"]
    assert p["entityName"] == "tasks" and p["item/subject"] == "Kick-off call"
    assert p["item/regardingobjectid_opportunity@odata.bind"] == f"opportunities({OPP})"
    assert p["item/ownerid@odata.bind"] == f"systemusers({OWNER})"
    assert p["item/scheduledend"].startswith("2026-11-24T09:00:00")
    assert p["item/description"] == "Won: Fabrikam laptop refresh for Fabrikam"
    mail = r.actions["Tell_finance"].inputs["parameters"]
    assert mail["emailMessage/Subject"] == "Deal won: Fabrikam laptop refresh"
    assert "value 12500 EUR" in mail["emailMessage/Body"]


def test_small_deal_gets_the_task_but_no_finance_mail():
    r = run_won(value=1800)
    assert r.ran("Create_kickoff_task") and not r.ran("Tell_finance")
    assert r.status == "Succeeded"


def test_the_threshold_is_five_thousand_inclusive():
    assert run_won(value=5000).ran("Tell_finance")
    assert not run_won(value=4999.99).ran("Tell_finance")


def test_a_second_win_of_the_same_deal_creates_no_second_task():
    r = run_won(existing=[{"activityid": "00000000-0000-0000-0000-0000000000d9"}])
    assert r.status == "Succeeded"
    assert not r.ran("Create_kickoff_task") and not r.ran("Tell_finance")


def test_the_duplicate_check_asks_for_this_opportunity_and_this_subject():
    r = run_won()
    p = r.actions["List_existing_kickoff_tasks"].inputs["parameters"]
    assert p["$filter"] == f"_regardingobjectid_value eq {OPP} and subject eq 'Kick-off call'"
    assert p["$top"] == 1 and check_filter(p["$filter"]) == []
    task = {"_regardingobjectid_value": OPP, "subject": "kick-off call"}
    assert evaluate_filter(p["$filter"], task)
    assert not evaluate_filter(p["$filter"], {**task, "_regardingobjectid_value": "00000000-0000-0000-0000-0000000000b9"})


def test_missing_estimate_counts_as_zero():
    m = won_mocks()
    m["Get_opportunity"]["body"].update(estimatedvalue=None, actualvalue=None)
    r = run_flow(load_flow(WON), sample("opportunity-won.json"), m, now=NOW)
    assert r.status == "Succeeded" and not r.ran("Tell_finance")


# ---------------------------------------------------------------------------------------------- the digest
def digest_mocks(rows):
    return {"List_overdue_opportunities": {"status": "Succeeded", "body": {"value": rows}},
            "Send_digest": {"status": "Succeeded", "body": {}}}


def overdue_row(name, account, owner, value, close):
    return {"name": name, "parentaccountid": {"name": account}, "estimatedvalue": value, "estimatedclosedate": close,
            "_ownerid_value@OData.Community.Display.V1.FormattedValue": owner}


def test_digest_sends_one_table_with_a_row_per_opportunity():
    rows = [overdue_row("Fabrikam laptop refresh", "Fabrikam", "Alex Demo", 12500, "2026-11-02"),
            overdue_row("Adatum chairs", "Adatum", "Sam Demo", 1800, "2026-11-20")]
    r = run_flow(load_flow(DIGEST), None, digest_mocks(rows), now=NOW)
    assert r.status == "Succeeded"
    mail = r.actions["Send_digest"].inputs["parameters"]
    assert mail["emailMessage/Subject"] == "Overdue opportunities: 2"
    body = mail["emailMessage/Body"]
    assert body.count("<tr>") == 3  # header + 2 rows
    assert "<td>Fabrikam laptop refresh</td><td>Fabrikam</td><td>Alex Demo</td><td>12500</td><td>2026-11-02</td>" in body


def test_digest_stays_quiet_when_nothing_is_overdue():
    r = run_flow(load_flow(DIGEST), None, digest_mocks([]), now=NOW)
    assert r.status == "Succeeded" and not r.ran("Send_digest") and not r.ran("Overdue_table")


def test_digest_query_is_valid_and_returns_exactly_the_overdue_open_rows():
    r = run_flow(load_flow(DIGEST), None, digest_mocks([]), now=NOW)
    p = r.actions["List_overdue_opportunities"].inputs["parameters"]
    assert p["$filter"] == "statecode eq 0 and estimatedclosedate lt 2026-11-21"
    assert check_filter(p["$filter"]) == []
    passed = [o["name"] for o in sample("opportunities-open.json") if evaluate_filter(p["$filter"], o)]
    # open and before 21 November: not the one closing today, not the future one, not the won one
    assert passed == ["Fabrikam laptop refresh", "Adatum chairs"]


def test_digest_query_pages_deterministically_and_stays_small():
    p = run_flow(load_flow(DIGEST), None, digest_mocks([]), now=NOW).actions["List_overdue_opportunities"].inputs["parameters"]
    # Learn: order on a unique column so pages don't overlap; $top (Row count) is fine because there is no paging here
    assert p["$orderby"].split(",")[-1].strip() == "opportunityid asc"
    assert p["$top"] == 50


def test_digest_runs_on_monday_morning_in_lisbon_time():
    rec = load_flow(DIGEST)["properties"]["definition"]["triggers"]["Every_Monday_morning"]["recurrence"]
    assert rec["schedule"] == {"weekDays": ["Monday"], "hours": ["8"], "minutes": [0]}
    assert rec["timeZone"] == "GMT Standard Time"
    assert rec["startTime"] == "2026-11-23T08:00:00"  # a Monday; Learn: the time zone applies only with a start time
