"""The happy path: an approved request gets a locked-down order folder, a summary file and a link back."""
from conftest import REQUESTS, ran


def test_approved_request_gets_a_folder_a_summary_and_a_link(lab):
    lab.approve()
    (run,) = lab.poller.poll()
    assert run.status == "Succeeded"
    assert lab.reference == "PR-00041"
    orders = lab.site.lists["Orders"]
    assert "PR-00041" in orders.folders
    summary = orders.files["PR-00041/PR-00041-summary.html"]
    assert "Laptops for two new developers" in summary["content"] and "12,500.00 EUR" in summary["content"]
    assert summary["fields"] == {"RequestId": 41, "RequestAmount": 12500}
    assert lab.fields["OrderFolder"] == "https://contoso.sharepoint.com/sites/Purchasing/Orders/PR-00041"
    (mail,) = lab.poller.mail
    assert mail["to"] == "alex.demo@contoso.com" and mail["subject"].startswith("PR-00041 is approved")


def test_the_requester_can_read_only_their_own_folder(lab):
    lab.approve()
    lab.poller.poll()
    site = lab.site
    roles = {v: k for k, v in site.role_definitions.items()}
    folder = site.folder("Orders", "PR-00041")
    assert folder.unique_permissions
    granted = {(pid, roles[rid]) for pid, rid in site.effective_role_assignments("Orders", "PR-00041")}
    owners, members = site.site_users["group:Purchasing Owners"]["Id"], site.site_users["group:Purchasing Members"]["Id"]
    # copyRoleAssignments=true keeps purchasing's access; Alex is added with Read; nobody else.
    assert granted == {(owners, "Full Control"), (members, "Edit"), (site.user_id("alex.demo@contoso.com"), "Read")}
    assert site.user_id("jordan.demo@contoso.com") is None


def test_the_write_back_triggers_one_quiet_run_and_then_it_stops(lab):
    lab.approve()
    assert lab.poller.poll_until_quiet() == 2
    first, second = [r for _, _, r in lab.poller.started_runs()]
    assert ran(first, "Create_order_folder") and ran(first, "Link_folder_on_request")
    # The second run sees our own write (OrderFolder): nothing to do, nothing written, so no third run.
    assert second.status == "Succeeded"
    assert second.status_of("Create_order_folder") == "Skipped"
    assert second.status_of("Mark_escalated") == "Skipped"
    assert len(lab.poller.mail) == 1


def test_creating_an_item_doesnt_trigger_and_pending_edits_dont_start_runs(lab):
    assert lab.poller.runs == []                         # creation is ignored by GetOnChangedItems
    lab.edit(lab.alex, Justification="Two laptops, 32 GB RAM, 1 TB SSD")
    (skipped,) = lab.poller.poll()
    assert skipped.status == "Skipped"                   # trigger condition false: no run in the history
    assert lab.site.lists["Orders"].folders == {}


def test_rejected_requests_are_left_alone(lab):
    lab.site.edit_item(REQUESTS, lab.item, {"Status": "Rejected", "DecisionBy": "Jordan Demo"}, lab.site.connection_user)
    assert [r.status for r in lab.poller.poll()] == ["Skipped"]


def test_the_flow_uses_rest_only_where_the_connector_has_no_action(lab):
    lab.approve()
    lab.poller.poll()
    ops = [op for op, _ in lab.site.calls]
    assert ops.count("HttpRequest") == 6                 # ensureuser, role, break, grant, entity type, MERGE
    rest = [target for op, target in lab.site.calls if op.startswith("REST")]
    assert rest == ["ensure_user", "role_definition", "break_inheritance", "add_role_assignment",
                    "entity_type", "merge_item"]
    assert {"CreateNewFolder", "CreateFile", "PatchFileItem", "GetItemChanges"} <= set(ops)
