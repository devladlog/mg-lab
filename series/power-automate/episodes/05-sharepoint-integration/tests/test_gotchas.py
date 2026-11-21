"""The traps, reproduced: a self-triggering loop, required columns on Update item, REST response shapes."""
import copy

from flowkit import lint
from spfake import Poller, first_version

from conftest import REQUESTS, Lab, actions, folder_block


def test_first_version_triggers_itself_forever(flow):
    lab = Lab(first_version(flow))
    lab.approve()
    busy = lab.poller.poll_until_quiet(max_polls=6)
    assert busy == 6                                     # never quiet: every run edits the item again
    assert len(lab.poller.mail) == 6                     # and Alex gets the same email every few minutes
    assert len(lab.site.lists["Orders"].folders) == 1    # (this fake returns the existing folder)


def test_the_linter_catches_the_loop_before_you_save(flow):
    msgs = [f.message for f in lint(first_version(flow)) if f.level == "warning"]
    assert any("infinite trigger loop" in m and "OrderFolder" in m for m in msgs)
    assert not any("infinite trigger loop" in m for m in (f.message for f in lint(flow)))


def test_update_item_needs_every_required_column(flow):
    """Learn: Update item needs a value for every mandatory column, which is why Mark escalated sends
    Title and Amount back unchanged, and why the folder link uses a REST MERGE that sends only OrderFolder."""
    broken = copy.deepcopy(flow)
    del actions(broken)["Amount_changed_after_approval"]["actions"]["Mark_escalated"]["inputs"]["parameters"]["item/Amount"]
    lab = Lab(flow)
    lab.approve()
    lab.poller.poll_until_quiet()
    lab.poller.flow = broken
    lab.edit(lab.alex, Amount=14200)
    (run,) = lab.poller.poll()
    assert run.status == "Failed"
    assert "Required column(s) missing: Amount" in run.actions["Mark_escalated"].error
    assert lab.fields["Status"] == "Approved"            # nothing was escalated, and purchasing wasn't told
    assert not any(m["to"] == "purchasing-team@contoso.com" for m in lab.poller.mail)


def test_without_nometadata_the_id_is_wrapped_and_the_grant_fails(flow):
    broken = copy.deepcopy(flow)
    folder_block(broken)["Ensure_requester"]["inputs"]["parameters"]["parameters/headers"] = {
        "Content-Type": "application/json;odata=verbose"}
    lab = Lab(broken)
    lab.approve()
    (run,) = lab.poller.poll()
    assert run.actions["Ensure_requester"].outputs["body"]["d"]["Id"] > 0   # the Id is there, one level down
    assert run.status_of("Grant_requester_read") == "Failed"               # principalid= is empty
    assert run.status == "Failed"
    assert any("odata=nometadata" in f.message for f in lint(broken))


def test_merge_without_the_entity_type_is_rejected(flow):
    broken = copy.deepcopy(flow)
    p = folder_block(broken)["Link_folder_on_request"]["inputs"]["parameters"]
    p["parameters/body"] = '{ "OrderFolder": "x" }'
    lab = Lab(broken)
    lab.approve()
    (run,) = lab.poller.poll()
    assert run.status_of("Link_folder_on_request") == "Failed"
    assert any("ListItemEntityTypeFullName" in f.message for f in lint(broken))


def test_a_wrong_library_path_fails_the_run_instead_of_leaving_an_open_folder(flow):
    lab = Lab(flow)
    lab.poller.params["Orders library path (cts_OrdersLibraryPath)"] = "/sites/Purchasing/Shared Documents"
    lab.approve()
    (run,) = lab.poller.poll()
    assert run.status_of("Break_inheritance") == "Failed"
    assert run.status_of("Grant_requester_read") == "Skipped"
    assert run.status_of("Link_folder_on_request") == "Skipped"   # no link to an unprotected folder
    assert run.status == "Failed"
    assert lab.fields["OrderFolder"] is None             # so the next edit retries the whole branch
