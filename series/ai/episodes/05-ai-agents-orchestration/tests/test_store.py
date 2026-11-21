"""Business rules in code: what the agent is allowed to do no matter what the model or the human says."""
from apagent.store import APPROVAL_LIMIT, InvoiceStore, load_policy, lookup_policy


def store():
    return InvoiceStore.load()


def test_queue_lists_only_invoices_in_review():
    ids = [i["id"] for i in store().queue()]
    assert ids == ["INV-2026-0142", "INV-2026-0088", "INV-2026-0311"]


def test_low_confidence_invoice_can_be_approved_with_a_note():
    s = store()
    r = s.approve("INV-2026-0088", "total checked against the scan", "Alex Demo")
    assert r == {"ok": True, "invoice_id": "INV-2026-0088", "message": "approved", "approved_by": "Alex Demo"}
    assert s.get("INV-2026-0088")["status"] == "approved"
    assert [i["id"] for i in s.queue()] == ["INV-2026-0142", "INV-2026-0311"]


def test_approval_is_idempotent():
    s = store()
    s.approve("INV-2026-0088", "checked", "Alex Demo")
    again = s.approve("inv-2026-0088 ", "checked twice", "Sam Demo")
    assert again["ok"] and again["message"] == "already approved" and again["approved_by"] == "Alex Demo"
    assert [e["action"] for e in s.events] == ["approved"]


def test_arithmetic_mismatch_is_never_approved():
    r = store().approve("INV-2026-0142", "looks fine", "Alex Demo")
    assert r["ok"] is False and r["error"] == "policy" and "corrected invoice" in r["message"]


def test_above_limit_goes_to_the_finance_manager():
    s = store()
    assert APPROVAL_LIMIT < 7800
    r = s.approve("INV-2026-0311", "urgent", "Alex Demo")
    assert r["ok"] is False and "finance manager" in r["message"]
    assert s.get("INV-2026-0311")["status"] == "review"


def test_new_supplier_needs_procurement_even_below_the_limit():
    s = store()
    s.invoices["INV-2026-0311"]["total"] = "780.00"
    r = s.approve("INV-2026-0311", "small amount", "Alex Demo")
    assert r["ok"] is False and "procurement" in r["message"]


def test_rejected_invoices_are_not_reopened():
    r = store().approve("INV-2026-0019", "please", "Alex Demo")
    assert r["ok"] is False and "not reopened" in r["message"]


def test_note_is_required_and_unknown_ids_are_reported():
    s = store()
    assert s.approve("INV-2026-0088", "  ", "Alex Demo")["message"] == "an approval note is required"
    assert s.approve("INV-9999", "x", "Alex Demo") == {"ok": False, "invoice_id": "INV-9999", "error": "not_found"}


def test_get_returns_a_copy_the_caller_cannot_mutate():
    s = store()
    inv = s.get("INV-2026-0088")
    inv["status"] = "approved"
    assert s.get("INV-2026-0088")["status"] == "review"


def test_policy_sections_and_lookup():
    policy = load_policy()
    assert list(policy) == ["Arithmetic mismatches", "Low-confidence reads", "Approval limits", "New suppliers",
                            "Rejected invoices"]
    assert "Fictional" not in " ".join(policy.values())  # the HTML comment is not policy text
    hits = [h["section"] for h in lookup_policy(policy, "approval limit")]
    assert "Approval limits" in hits
    assert lookup_policy(policy, "xyz") == []
