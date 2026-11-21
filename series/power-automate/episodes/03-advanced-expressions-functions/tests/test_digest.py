"""The weekly purchasing digest, dry-run end to end with a fake SharePoint and a fake mailbox."""
import copy

import pytest

from flowkit import run_flow
from flowkit.expr import Context, evaluate

from conftest import SUMMER_RUN, WINTER_RUN, actions, mocks, sample


def run(flow, now=SUMMER_RUN, items=None):
    sent = []
    result = run_flow(flow, None, mocks(items, sent), now=now)
    return result, sent


def test_week_window_is_last_monday_to_monday_in_lisbon_time(digest):
    r, _ = run(digest)
    assert r.actions["Week_start_local"].outputs == "2026-07-06T00:00:00.0000000"   # no offset
    assert r.actions["Week_start_utc"].outputs == "2026-07-05T23:00:00Z"            # 00:00 WEST is 23:00 UTC
    assert r.actions["Week_end_utc"].outputs == "2026-07-12T23:00:00Z"
    assert r.actions["Get_requests"].inputs["parameters"]["$filter"] == \
        "Created ge '2026-07-05T23:00:00Z' and Created lt '2026-07-12T23:00:00Z'"


def test_in_winter_lisbon_midnight_is_utc_midnight(digest):
    r, _ = run(digest, now=WINTER_RUN)
    assert r.actions["Week_start_utc"].outputs == "2026-01-05T00:00:00Z"
    assert r.actions["Week_end_utc"].outputs == "2026-01-12T00:00:00Z"


def test_rows_are_shaped_by_one_select(digest):
    r, _ = run(digest)
    rows = {row["reference"]: row for row in r.actions["Rows"].outputs["body"]}
    assert set(rows) == {"PR-00046", "PR-00041", "PR-00042", "PR-00043", "PR-00044"}   # approved, in the window
    assert rows["PR-00041"] == {"reference": "PR-00041", "costCentre": "CC-4100",
                                "item": "Laptops for two new developers", "requester": "Alex Demo",
                                "amount": 12500, "submitted": "07/07/2026 10:15"}       # 09:15 UTC is 10:15 in Lisbon
    assert rows["PR-00043"]["costCentre"] == "CC-2200"      # '[cc-2200]': startsWith is case-insensitive, toUpper
    assert rows["PR-00044"]["costCentre"] == "Unassigned"   # no '[CC-...]' prefix
    assert rows["PR-00044"]["item"] == "Conference tickets"
    assert rows["PR-00046"]["submitted"] == "06/07/2026 00:30"   # created 23:30 UTC on Sunday


@pytest.mark.parametrize("title, cost_centre, item", [
    ("[CC-4100] Laptops", "CC-4100", "Laptops"),
    ("[cc-4100]   Laptops  ", "CC-4100", "Laptops"),
    ("Laptops", "Unassigned", "Laptops"),
    ("[CC-4100 Laptops", "Unassigned", "[CC-4100 Laptops"),   # no closing bracket: nothing is cut off
    ("[] Laptops", "Unassigned", "Laptops"),
])
def test_title_parsing_never_fails(digest, title, cost_centre, item):
    select = actions(digest)["Rows"]["inputs"]["select"]
    ctx = Context()
    ctx.item_stack.append({"Title": title})
    assert evaluate(select["costCentre"], ctx) == cost_centre
    assert evaluate(select["item"], ctx) == item


def test_total_group_by_and_top_three_without_a_loop(digest):
    r, _ = run(digest)
    assert r.actions["Total"].outputs == 19720.5
    assert r.actions["By_cost_centre"].outputs["body"] == [
        {"costCentre": "CC-2200", "requests": 1, "total": 4350.5},
        {"costCentre": "CC-3300", "requests": 1, "total": 120},
        {"costCentre": "CC-4100", "requests": 2, "total": 14300},
        {"costCentre": "Unassigned", "requests": 1, "total": 950},
    ]
    assert [row["reference"] for row in r.actions["Top_three"].outputs] == ["PR-00041", "PR-00043", "PR-00042"]
    assert not any(a.get("type") in ("Foreach", "Until") for a in _all_actions(digest))


def test_email_subject_and_tables(digest):
    r, sent = run(digest)
    assert r.status == "Succeeded"
    (mail,) = sent
    assert mail["emailMessage/To"] == "finance-approvers@contoso.com"
    assert mail["emailMessage/Subject"] == "Approved purchases, week of 6 July 2026: 19,720.50 EUR"
    body = mail["emailMessage/Body"]
    assert body.startswith("<p>5 approved purchase requests submitted between Monday 6 July and Sunday 12 July")
    assert "<td>CC-4100</td><td>2</td><td>14,300.00</td>" in body
    assert "<td>PR-00043</td><td>Ergonomic chairs for the support team</td><td>Jordan Demo</td><td>4,350.50</td>" in body


def test_no_email_when_nothing_was_approved(digest):
    items = [i for i in sample("purchase-requests.json")["value"] if i["Status"]["Value"] != "Approved"]
    r, sent = run(digest, items=items)
    assert r.status == "Succeeded"
    assert sent == []
    assert r.status_of("Send_digest") == "Skipped"


def test_one_request_is_still_a_list(digest):
    # A single <row> must still sum and group correctly.
    items = [i for i in sample("purchase-requests.json")["value"] if i["ID"] == 41]
    r, sent = run(digest, items=items)
    assert r.actions["Total"].outputs == 12500
    assert r.actions["By_cost_centre"].outputs["body"] == [{"costCentre": "CC-4100", "requests": 1, "total": 12500}]
    assert sent and "12,500.00 EUR" in sent[0]["emailMessage/Subject"]


def _all_actions(flow):
    from flowkit.lint import iter_actions
    return [a for _, a, *_ in iter_actions(actions(flow))]
