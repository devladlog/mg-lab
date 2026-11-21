from __future__ import annotations

import copy
import json

import pytest

from conftest import DEMO, load_json, run_cli
from review_kit import comments

ITEMS = load_json(DEMO / "review-comments.json")


@pytest.mark.parametrize("body,label,deco,subject", [
    ("praise: Nice and small.", "praise", (), "Nice and small."),
    ("issue (blocking): this throws", "issue", ("blocking",), "this throws"),
    ("Suggestion (non-blocking, test): add a case\n\nmore text", "suggestion", ("non-blocking", "test"), "add a case"),
    ("todo(blocking):no space", "todo", ("blocking",), "no space"),
    ("LGTM", None, (), "LGTM"),
    ("hmm: not a label", None, (), "hmm: not a label"),
    ("", None, (), ""),
])
def test_parse_body(body, label, deco, subject):
    assert comments.parse_body(body) == (label, deco, subject)


def test_the_demo_review_is_clean_and_has_three_blocking_comments():
    parsed = comments.load(ITEMS)
    assert comments.lint(parsed) == []
    s = comments.summarize(parsed)
    assert (s["comments"], s["replies"]) == (7, 2)
    assert s["labels"] == {"praise": 1, "issue": 1, "question": 1, "suggestion": 1, "todo": 1, "nitpick": 1, "thought": 1}
    assert [c.label for c in s["blocking"]] == ["issue", "question", "todo"]


def test_replies_are_conversation_not_feedback():
    items = copy.deepcopy(ITEMS)
    items.append({"id": 999, "path": "x", "line": 1, "body": "thanks!", "user": {"login": "alex-demo"}, "in_reply_to_id": 101})
    assert comments.lint(comments.load(items)) == []


def test_house_rules():
    def lint(body):
        return comments.lint(comments.load([{"id": 1, "path": "a.cs", "line": 3, "body": body, "user": {"login": "sam-demo"}}]))
    assert lint("looks off") == ["a.cs:3: no label. Start with one of: praise, nitpick, suggestion, issue, todo, question, thought, chore, note"]
    for label in ("issue", "question", "todo", "chore"):
        assert lint(f"{label}: x") == [f"a.cs:3: '{label}' must say (blocking) or (non-blocking)"]
        assert lint(f"{label} (non-blocking): x") == [] and lint(f"{label} (blocking): x") == []
    assert lint("nitpick (blocking): x") == ["a.cs:3: 'nitpick' can't be blocking: use issue, todo or chore"]
    assert lint("praise: x") == [] and lint("suggestion: x") == []


def test_the_suggestion_block_in_the_demo_review_is_a_github_suggestion():
    body = next(i["body"] for i in ITEMS if i["id"] == 102)
    assert "```suggestion\n" in body and "is not { } order) return Results.NotFound();\n    order.Status = \"cancelled\";" in body


def test_cli_prints_the_summary_and_fails_on_lint_problems(tmp_path):
    ok = run_cli("comments", str(DEMO / "review-comments.json"), env={"GITHUB_STEP_SUMMARY": ""})
    assert ok.returncode == 0 and "Blocking (3)" in ok.stdout
    bad = copy.deepcopy(ITEMS)
    bad[1]["body"] = "this is wrong"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(bad))
    res = run_cli("comments", str(p), env={"GITHUB_STEP_SUMMARY": ""})
    assert res.returncode == 1 and "no label" in res.stdout
    assert run_cli("comments", str(tmp_path / "missing.json")).returncode == 2


def test_the_review_payload_has_the_shape_of_the_create_review_api():
    import importlib.util
    spec = importlib.util.spec_from_file_location("review_payload", DEMO / "review-payload.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    body = mod.payload(ITEMS)
    assert body["event"] == "COMMENT" and body["body"]                          # body is required for COMMENT
    assert len(body["comments"]) == 7                                           # the replies are not part of the review
    assert all(set(c) >= {"path", "line", "side", "body"} for c in body["comments"])
    issue = next(c for c in body["comments"] if c["body"].startswith("issue (blocking)"))
    assert (issue["start_line"], issue["line"], issue["start_side"]) == (54, 55, "RIGHT")   # a multi-line suggestion
    assert sum("start_line" in c for c in body["comments"]) == 1
    assert "commit_id" not in body                                              # defaults to the latest commit of the PR
