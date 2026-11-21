"""Dry-run the scheduled 'IT requests daily digest' flow."""
from flowkit import run_flow

from conftest import NOW, sample


def run_with(items, digest):
    mocks = {"Get_open_requests": {"status": "Succeeded", "body": items},
             "Send_digest": {"status": "Succeeded", "body": {}}}
    return run_flow(digest, None, mocks, now=NOW)


def test_digest_lists_open_requests_and_counts_overdue(digest):
    run = run_with(sample("get-items-open.json"), digest)
    assert run.status == "Succeeded"
    assert run.actions["Get_open_requests"].inputs["parameters"]["$filter"] == "Status ne 'Done'"
    overdue = run.actions["Overdue_requests"].outputs["body"]
    assert [i["ID"] for i in overdue] == [42]               # due 08:00, it's 09:00
    email = run.actions["Send_digest"].inputs["parameters"]
    assert email["emailMessage/Subject"] == "IT requests: 3 open, 1 overdue"
    assert email["emailMessage/Body"].startswith("<p>Open requests on Monday 05 Jan:</p><table>")
    assert email["emailMessage/Body"].count("<tr>") == 4    # header + 3 rows
    assert "<td>-</td>" in email["emailMessage/Body"]      # no due date yet


def test_no_open_requests_means_no_email(digest):
    run = run_with({"value": []}, digest)
    assert run.status == "Succeeded"
    assert run.status_of("Send_digest") == "Skipped"
