"""Get changes for an item: which columns changed in this trigger window, not just what the item looks like now."""
import copy

from spfake import Poller

from conftest import REQUESTS, Lab, ran


def approved_with_folder(flow):
    lab = Lab(flow)
    lab.approve()
    lab.poller.poll_until_quiet()
    lab.poller.mail.clear()
    return lab


def test_amount_changed_after_approval_is_escalated(flow):
    lab = approved_with_folder(flow)
    lab.edit(lab.alex, Amount=14200)
    (run,) = lab.poller.poll()
    assert ran(run, "Mark_escalated") and ran(run, "Notify_purchasing")
    assert run.status_of("Create_order_folder") == "Skipped"
    assert lab.fields["Status"] == "Escalated"
    assert lab.fields["DecisionComments"] == ("Amount changed to 14,200.00 EUR after approval by Alex Demo. "
                                              "Needs a new decision.")
    (mail,) = lab.poller.mail
    assert mail["to"] == "purchasing-team@contoso.com" and mail["importance"] == "High"
    # Escalated no longer matches the trigger condition: the flow's own write doesn't start another run.
    assert [r.status for r in lab.poller.poll()] == ["Skipped"]


def test_other_edits_after_approval_do_nothing(flow):
    lab = approved_with_folder(flow)
    lab.edit(lab.alex, Justification="Two developer laptops, 32 GB RAM, docking stations not included")
    (run,) = lab.poller.poll()
    assert run.status == "Succeeded"
    assert run.status_of("Mark_escalated") == "Skipped"
    assert lab.fields["Status"] == "Approved" and lab.poller.mail == []


def test_get_changes_compares_the_trigger_window_not_the_whole_history(flow):
    lab = approved_with_folder(flow)
    lab.edit(lab.alex, Justification="clarified")         # window 1: only Justification
    (run,) = lab.poller.poll()
    changed = run.actions["Get_changes"].outputs["body"]["ColumnHasChanged"]
    assert changed["Justification"] is True
    assert changed["Amount"] is False and changed["Status"] is False   # they changed earlier, not in this window


def test_changes_inside_one_polling_window_are_merged(flow):
    """Learn: a run "may gather more than one change". If the amount is edited in the same window as the
    approval, Get changes reports both columns, and the flow can't tell which came first."""
    lab = Lab(flow)
    lab.approve()
    lab.edit(lab.alex, Amount=14200)                      # before the next poll
    (run,) = lab.poller.poll()
    changed = run.actions["Get_changes"].outputs["body"]["ColumnHasChanged"]
    assert changed["Amount"] and changed["Status"]
    assert run.status_of("Mark_escalated") == "Skipped"   # treated as approved with the new amount
    assert ran(run, "Create_order_folder")


def test_get_changes_needs_versioning(flow):
    lab = Lab(flow)
    lab.site.lists[REQUESTS].versioning = False
    lab.approve()
    (run,) = lab.poller.poll()
    assert run.status == "Failed"
    assert run.status_of("Get_changes") == "Failed"
    assert run.status_of("Create_order_folder") == "Skipped"
