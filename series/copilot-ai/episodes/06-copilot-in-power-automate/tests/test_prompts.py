import pytest

from copilot_flow_review.prompts import lint_prompt
from conftest import ROOT

LINES = [l.split("\t", 1) for l in (ROOT / "src" / "samples" / "prompts.txt").read_text(encoding="utf-8").splitlines()
         if l and not l.startswith("#")]
PROMPTS = {i: (m, p) for i, (m, p) in enumerate(LINES)}


def codes(text, mode):
    return {f.code for f in lint_prompt(text, mode)}


def test_a_good_create_prompt_is_clean():
    mode, text = PROMPTS[0]
    assert mode == "create"
    assert lint_prompt(text, mode) == []


def test_vague_create_prompt_gets_the_three_learn_warnings():
    mode, text = PROMPTS[1]
    assert codes(text, mode) == {"PL001", "PL002", "PL003"}


def test_learn_example_prompts_pass():
    # Examples taken from "Create your first cloud flow using Copilot" and the tips page.
    assert lint_prompt("When an email arrives, I want to post the subject of the email to 'Contoso' Teams General channel", "create") == []
    assert lint_prompt("When an item is created in SharePoint, send me a mobile notification.", "create") == []
    assert lint_prompt("Add a condition after the Get Items action that checks if the Status column equals 'Approved'.", "edit") == []
    assert lint_prompt("Change the trigger to run every Monday at 9:00 AM Pacific Time.", "edit") == []


def test_edit_prompts_from_the_samples():
    assert lint_prompt(*reversed(PROMPTS[2])) == []
    assert lint_prompt(*reversed(PROMPTS[3])) == []


def test_fix_my_flow_is_an_error_in_edit_mode():
    mode, text = PROMPTS[4]
    found = {f.code: f for f in lint_prompt(text, mode)}
    assert found["PL005"].severity == "error"


def test_debugging_questions_are_flagged_because_the_designer_cannot_see_runs():
    mode, text = PROMPTS[5]
    assert "PL007" in codes(text, mode)
    assert "PL007" in codes("Debug this error: 'The requested operation is invalid.'", "edit")


def test_data_questions_are_flagged():
    assert "PL008" in codes("What columns does my SharePoint list have?", "edit")
    assert "PL008" in codes("Is the email address in my Dataverse contact table valid?", "edit")


def test_the_long_chain_from_the_learn_tips_page_is_too_many_steps_for_one_edit_message():
    chain = ("Add a trigger for when a SharePoint item is created, then get the item details, check if the status is approved, "
             "send an email to the manager, wait for approval, update the item, and post to Teams.")
    assert "PL004" in codes(chain, "edit")


def test_multi_step_is_fine_in_create_mode():
    # Learn: on the Home page, describe in detail how you want the automation to work.
    assert "PL004" not in codes("When a loan is overdue, get the borrower, send an email in Outlook, then post in Teams and update the list", "create")


def test_empty_prompt_and_bad_mode():
    assert [f.code for f in lint_prompt("   ")] == ["PL000"]
    with pytest.raises(ValueError):
        lint_prompt("x", "chat")
